#!/usr/bin/env python3
"""Mutation driver: applies one source mutation at a time, runs the project's suite, restores the file from the copy taken before the edit and verifies that restore by checksum."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

ROTTED = "ROTTED"
REJECTED_COMPILE = "REJECTED_COMPILE"
REJECTED_COLLECTION = "REJECTED_COLLECTION"
REJECTED_ALL_RED = "REJECTED_ALL_RED"
REJECTED_NO_RESULT = "REJECTED_NO_RESULT"
REJECTED_TIMEOUT = "REJECTED_TIMEOUT"
SURVIVED = "SURVIVED"
CAUGHT = "CAUGHT"
VERDICTS = (CAUGHT, SURVIVED, REJECTED_COMPILE, REJECTED_COLLECTION, REJECTED_ALL_RED, REJECTED_NO_RESULT, REJECTED_TIMEOUT, ROTTED)

# Every pattern here is fnmatch over the repo-relative POSIX path, where `*` spans `/`.
DEFAULT_PROTECTED = (
    "*.test.*",
    "*.spec.*",
    "*_test.*",
    "test_*",
    "*/test_*",
    "*.feature",
    "*.snap",
    "test/*",
    "tests/*",
    "*/test/*",
    "*/tests/*",
    "*/__tests__/*",
    "*/__fixtures__/*",
    "*/__snapshots__/*",
)
DEFAULT_BUCKETS = {"all": ("*",)}
DEFAULT_STATE = ".tmp/mutate"
BASELINE_TIMEOUT_SEC = 1800.0
COMPILE_TIMEOUT_SEC = 600.0
TIMEOUT_FLOOR_SEC = 60.0
TIMEOUT_BASELINE_FACTOR = 10.0
MUTATION_KEYS = {"id", "file", "old", "new", "note"}
IDENTITY_SEPARATOR = " :: "

EXIT_OK = 0
EXIT_ROT = 1
EXIT_REFUSED = 2
EXIT_ABORTED = 3


class Refuse(Exception):
    pass


class Abort(Exception):
    pass


class Rot(Exception):
    pass


@dataclass(frozen=True)
class Runner:
    command: tuple[str, ...]
    cwd: Path
    format: str
    timeout_sec: float | None


@dataclass(frozen=True)
class Config:
    repo: Path
    state: Path
    runner: Runner
    compile_command: tuple[str, ...]
    compile_cwd: Path
    compile_timeout_sec: float
    mutable: tuple[str, ...]
    protected: tuple[str, ...]
    buckets: dict[str, tuple[str, ...]]
    mutations: tuple[dict[str, str], ...]

    @property
    def results(self) -> Path:
        return self.state / "results.jsonl"

    @property
    def baseline_file(self) -> Path:
        return self.state / "baseline.json"

    @property
    def marker(self) -> Path:
        return self.state / "ABORT"


@dataclass(frozen=True)
class Case:
    file: str
    name: str
    failed: bool

    @property
    def identity(self) -> str:
        return f"{self.file}{IDENTITY_SEPARATOR}{self.name}"


@dataclass(frozen=True)
class Completed:
    launched: bool
    code: int | None
    seconds: float
    output: str
    timed_out: bool


@dataclass(frozen=True)
class Measurement:
    files: int
    tests: int
    identities: tuple[str, ...]
    failed: tuple[str, ...]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def git(repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *arguments], capture_output=True, text=True, check=False)


def as_strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise Refuse(f"{label} must be a non-empty list of non-empty strings")
    return tuple(value)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise Refuse(f"cannot read {path}: {error}") from error
    except ValueError as error:
        raise Refuse(f"{path} is not valid JSON: {error}") from error


def load_mutations(source: Any, origin: Path) -> list[dict[str, str]]:
    if not isinstance(source, list):
        raise Refuse(f"{origin}: mutations must be a list")
    loaded = []
    for index, mutation in enumerate(source):
        where = f"{origin}: mutation {index}"
        if not isinstance(mutation, dict):
            raise Refuse(f"{where} is not an object")
        unknown = sorted(set(mutation) - MUTATION_KEYS)
        if unknown:
            raise Refuse(f"{where} carries unknown key(s): {', '.join(unknown)}")
        for key in ("id", "file", "old", "new"):
            if not isinstance(mutation.get(key), str) or not mutation[key]:
                raise Refuse(f"{where} needs a non-empty string '{key}'")
        if mutation["old"] == mutation["new"]:
            raise Refuse(f"{where} ({mutation['id']}) replaces the anchor with itself")
        loaded.append({key: str(mutation.get(key, "")) for key in MUTATION_KEYS})
    return loaded


def load_config(path: Path, extra_mutations: list[Path]) -> Config:
    document = read_json(path)
    if not isinstance(document, dict):
        raise Refuse(f"{path} must hold a JSON object")
    here = path.resolve().parent

    stated_repo = document.get("repo")
    if isinstance(stated_repo, str):
        repo = (here / stated_repo).resolve()
    else:
        toplevel = git(here, "rev-parse", "--show-toplevel")
        if toplevel.returncode != 0:
            raise Refuse(f"{here} is not inside a git repository and the config names no 'repo'")
        repo = Path(toplevel.stdout.strip()).resolve()
    if not repo.is_dir():
        raise Refuse(f"repo {repo} is not a directory")

    runner = document.get("runner")
    if not isinstance(runner, dict):
        raise Refuse(f"{path} needs a 'runner' object")
    fmt = runner.get("format")
    if fmt not in PARSERS:
        raise Refuse(f"runner.format must be one of {', '.join(sorted(PARSERS))}")
    timeout = runner.get("timeoutSec")
    if timeout is not None and not (isinstance(timeout, (int, float)) and timeout > 0):
        raise Refuse("runner.timeoutSec must be a positive number")

    compiler = document.get("compile", {})
    if not isinstance(compiler, dict):
        raise Refuse("compile must be an object")
    compile_timeout = compiler.get("timeoutSec", COMPILE_TIMEOUT_SEC)
    if not (isinstance(compile_timeout, (int, float)) and compile_timeout > 0):
        raise Refuse("compile.timeoutSec must be a positive number")

    buckets = document.get("buckets")
    if buckets is None:
        grouped_patterns = dict(DEFAULT_BUCKETS)
    elif isinstance(buckets, dict) and buckets:
        grouped_patterns = {name: as_strings(patterns, f"buckets.{name}") for name, patterns in buckets.items()}
    else:
        raise Refuse("buckets must be a non-empty object of name -> patterns")

    mutations = load_mutations(document.get("mutations", []), path)
    for extra in extra_mutations:
        mutations.extend(load_mutations(read_json(extra), extra))
    seen: set[str] = set()
    for mutation in mutations:
        if mutation["id"] in seen:
            raise Refuse(f"duplicate mutation id: {mutation['id']}")
        seen.add(mutation["id"])

    return Config(
        repo=repo,
        state=(repo / str(document.get("state", DEFAULT_STATE))).resolve(),
        runner=Runner(
            command=as_strings(runner.get("command"), "runner.command"),
            cwd=(repo / str(runner.get("cwd", "."))).resolve(),
            format=str(fmt),
            timeout_sec=float(timeout) if timeout else None,
        ),
        compile_command=as_strings(compiler["command"], "compile.command") if "command" in compiler else (),
        compile_cwd=(repo / str(compiler.get("cwd", "."))).resolve(),
        compile_timeout_sec=float(compile_timeout),
        mutable=as_strings(document.get("mutable"), "mutable"),
        protected=tuple(document["protected"]) if isinstance(document.get("protected"), list) else DEFAULT_PROTECTED,
        buckets=grouped_patterns,
        mutations=tuple(mutations),
    )


def relative(path: str, repo: Path) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(repo).as_posix()
    except ValueError:
        return candidate.as_posix()


def parse_vitest_json(text: str, repo: Path) -> list[Case]:
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError("the report is not a JSON object")
    cases = []
    for suite in document.get("testResults") or []:
        path = relative(str(suite.get("name") or ""), repo)
        for assertion in suite.get("assertionResults") or []:
            cases.append(Case(path, str(assertion.get("fullName") or assertion.get("title") or ""), assertion.get("status") == "failed"))
    return cases


def parse_junit(text: str, repo: Path) -> list[Case]:
    root = ElementTree.fromstring(text)
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    cases = []
    for suite in suites:
        fallback = str(suite.get("file") or suite.get("name") or "")
        for case in suite.iter("testcase"):
            path = relative(str(case.get("file") or case.get("classname") or fallback), repo)
            failed = any(child.tag in ("failure", "error") for child in case)
            cases.append(Case(path, str(case.get("name") or ""), failed))
    return cases


PARSERS: dict[str, Callable[[str, Path], list[Case]]] = {"vitest-json": parse_vitest_json, "junit": parse_junit}
EXTENSIONS = {"vitest-json": "json", "junit": "xml"}


def measured(cases: list[Case]) -> Measurement:
    return Measurement(
        files=len({case.file for case in cases}),
        tests=len(cases),
        identities=tuple(case.identity for case in cases),
        failed=tuple(case.identity for case in cases if case.failed),
    )


def run_process(command: tuple[str, ...], cwd: Path, timeout: float, log: Path) -> Completed:
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        # Its own session, so the timeout below kills the runner's workers with it.
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
    except OSError as error:
        log.write_text(str(error), encoding="utf-8")
        return Completed(launched=False, code=None, seconds=0.0, output=str(error), timed_out=False)
    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            process.kill()
        output, _ = process.communicate()
    log.write_text(output or "", encoding="utf-8")
    return Completed(launched=True, code=process.returncode, seconds=time.monotonic() - started, output=output or "", timed_out=timed_out)


def expand(argument: str, config: Config, report: Path | None = None) -> str:
    expanded = argument.replace("{state}", str(config.state)).replace("{repo}", str(config.repo))
    return expanded if report is None else expanded.replace("{report}", str(report))


def run_suite(config: Config, tag: str, timeout: float) -> tuple[Measurement | None, Completed, str]:
    report = config.state / "reports" / f"{tag}.{EXTENSIONS[config.runner.format]}"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.unlink(missing_ok=True)
    command = tuple(expand(argument, config, report) for argument in config.runner.command)
    completed = run_process(command, config.runner.cwd, timeout, config.state / "logs" / f"{tag}.log")
    if not completed.launched:
        return None, completed, f"the runner could not be started: {completed.output}"
    if completed.timed_out:
        return None, completed, f"the suite did not finish within {timeout:.0f}s"
    if not report.exists():
        return None, completed, f"the runner left no report at {report}"
    try:
        cases = PARSERS[config.runner.format](report.read_text(encoding="utf-8", errors="replace"), config.repo)
    except (ValueError, ElementTree.ParseError) as error:
        return None, completed, f"unparseable {config.runner.format} report: {error}"
    return measured(cases), completed, ""


def target_of(config: Config, stated: str) -> Path:
    if os.path.isabs(stated):
        raise Refuse(f"a mutation path is relative to the repository: {stated}")
    target = (config.repo / stated).resolve()
    try:
        inside = target.relative_to(config.repo).as_posix()
    except ValueError:
        raise Refuse(f"{stated} resolves outside the repository") from None
    if not any(fnmatch.fnmatch(inside, pattern) for pattern in config.mutable):
        raise Refuse(f"{inside} matches no 'mutable' pattern")
    for pattern in config.protected:
        if fnmatch.fnmatch(inside, pattern):
            raise Refuse(f"{inside} is test material (protected pattern {pattern}) — mutating it proves nothing")
    return target


def scope_status(config: Config) -> str:
    status = git(config.repo, "status", "--porcelain", "--", *config.mutable)
    if status.returncode != 0:
        raise Refuse(f"git status failed in {config.repo}: {status.stderr.strip()}")
    return status.stdout.strip()


def refuse_when_dirty(config: Config) -> None:
    dirty = scope_status(config)
    if dirty:
        raise Refuse(f"the mutable scope is dirty before the run — refusing to start:\n{dirty}")


def refuse_when_marked(config: Config) -> None:
    if config.marker.exists():
        raise Refuse(f"a previous run aborted; read it, inspect the tree and delete {config.marker} by hand before continuing:\n{config.marker.read_text(encoding='utf-8').strip()}")


def require_ignored_state(config: Config) -> None:
    if git(config.repo, "check-ignore", "-q", str(config.state)).returncode != 0:
        raise Refuse(f"the state directory {config.state} is not ignored by git — add it to .gitignore")
    config.state.mkdir(parents=True, exist_ok=True)


def abort(config: Config, message: str) -> Abort:
    config.state.mkdir(parents=True, exist_ok=True)
    config.marker.write_text(f"{datetime.now(timezone.utc).isoformat()}\n{message}\n", encoding="utf-8")
    return Abort(f"{message}\nthe tree may be dirty — inspect it, then delete {config.marker}")


def records_of(config: Config) -> list[dict[str, Any]]:
    if not config.results.exists():
        return []
    records = []
    for number, line in enumerate(config.results.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError as error:
            raise Refuse(f"{config.results}:{number} is not valid JSON: {error}") from error
    return records


def append_record(config: Config, record: dict[str, Any]) -> None:
    config.results.parent.mkdir(parents=True, exist_ok=True)
    with config.results.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def bucket_of(config: Config, identity: str) -> str:
    path = identity.split(IDENTITY_SEPARATOR, 1)[0]
    for name, patterns in config.buckets.items():
        if any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
            return name
    return "other"


def grouped(config: Config, identities: tuple[str, ...]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for identity in identities:
        groups.setdefault(bucket_of(config, identity), []).append(identity)
    return groups


def baseline_of(config: Config) -> dict[str, Any]:
    if not config.baseline_file.exists():
        raise Refuse(f"no baseline at {config.baseline_file} — run the baseline command first")
    return read_json(config.baseline_file)


def suite_timeout(config: Config, baseline: dict[str, Any]) -> float:
    if config.runner.timeout_sec:
        return config.runner.timeout_sec
    return max(TIMEOUT_FLOOR_SEC, TIMEOUT_BASELINE_FACTOR * float(baseline.get("seconds") or 0.0))


def announce_rot(records: list[dict[str, Any]]) -> int:
    rotted = [record for record in records if record.get("verdict") == ROTTED]
    if not rotted:
        return EXIT_OK
    print(f"\nROTTED — {len(rotted)} mutation(s) never ran, so nothing they were meant to prove is proven:")
    for record in rotted:
        print(f"  {record['id']}  {record['file']}  {record.get('detail', '')}")
    return EXIT_ROT


def announce_marker(config: Config) -> int:
    if not config.marker.exists():
        return EXIT_OK
    print(f"\nABORTED — {config.marker} stands; the records above stop at the abort.")
    return EXIT_ROT


def cmd_baseline(config: Config, args: argparse.Namespace) -> int:
    refuse_when_marked(config)
    require_ignored_state(config)
    if config.baseline_file.exists() and not args.force:
        baseline = baseline_of(config)
        print(f"baseline already measured: {baseline['files']} file(s), {baseline['tests']} test(s), {baseline['seconds']:.1f}s")
        return EXIT_OK
    refuse_when_dirty(config)
    print("measuring the unmutated baseline", flush=True)
    measurement, completed, detail = run_suite(config, "baseline", config.runner.timeout_sec or BASELINE_TIMEOUT_SEC)
    if measurement is None:
        raise Refuse(f"the baseline run produced no result: {detail}\nlog: {config.state / 'logs' / 'baseline.log'}")
    if not measurement.tests:
        raise Refuse("the baseline run collected no tests at all")
    if measurement.failed:
        listed = "\n".join(f"  {identity}" for identity in measurement.failed[:10])
        raise Refuse(f"the baseline suite is not green: {len(measurement.failed)} of {measurement.tests} failed — red against a red baseline proves nothing\n{listed}")
    config.baseline_file.write_text(json.dumps({"files": measurement.files, "tests": measurement.tests, "seconds": round(completed.seconds, 3), "identities": list(measurement.identities)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"baseline: {measurement.files} file(s), {measurement.tests} test(s), {completed.seconds:.1f}s")
    return EXIT_OK


def stamp(target: Path, clock: float) -> float:
    # A cache keyed on whole-second mtimes — CPython's .pyc among them — serves the previous
    # mutation's build when two same-size mutations land inside one second, so each is stamped later
    # than the last. The restore below puts the mtime back in the past, which invalidates it again.
    when = max(clock, time.time()) + 1.0
    os.utime(target, (when, when))
    return when


def apply_mutation(config: Config, mutation: dict[str, str], target: Path, backup: Path, clock: float) -> tuple[str, str, float]:
    if not target.is_file():
        raise Rot(f"no such file: {mutation['file']}")
    before = md5(target)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target, backup)
    source = target.read_text(encoding="utf-8")
    hits = source.count(mutation["old"])
    if hits != 1:
        backup.unlink(missing_ok=True)
        raise Rot(f"the anchor occurs {hits}x in {mutation['file']}; it must occur exactly once")
    target.write_text(source.replace(mutation["old"], mutation["new"], 1), encoding="utf-8")
    after = md5(target)
    if after == before:
        raise abort(config, f"writing mutation {mutation['id']} left {mutation['file']} byte-identical")
    return before, after, stamp(target, clock)


def restore(config: Config, mutation: dict[str, str], target: Path, backup: Path, before: str, sabotage: str | None) -> None:
    # --sabotage-restore corrupts the copy so a genuinely bad restore happens: the checksum below must catch it.
    if sabotage == mutation["id"]:
        backup.write_bytes(backup.read_bytes() + b"\n")
    shutil.copyfile(backup, target)
    now = md5(target)
    if now != before:
        raise abort(config, f"restoring {mutation['file']} for mutation {mutation['id']} produced md5 {now}, expected {before}; the copy is at {backup}")
    dirty = scope_status(config)
    if dirty:
        raise abort(config, f"after restoring mutation {mutation['id']} the mutable scope is dirty:\n{dirty}")


def score(config: Config, baseline: dict[str, Any], measurement: Measurement | None, detail: str, completed: Completed) -> dict[str, Any]:
    seconds = round(completed.seconds, 3)
    if measurement is None:
        return {"verdict": REJECTED_TIMEOUT if completed.timed_out else REJECTED_NO_RESULT, "detail": detail, "seconds": seconds}
    common = {"failed": len(measurement.failed), "total": measurement.tests, "seconds": seconds}
    if measurement.files != baseline["files"] or measurement.tests != baseline["tests"]:
        return {**common, "verdict": REJECTED_COLLECTION, "detail": f"collected {measurement.files}/{baseline['files']} file(s) and {measurement.tests}/{baseline['tests']} test(s) — the mutation is not the program the baseline measured"}
    if len(measurement.failed) == measurement.tests:
        return {**common, "verdict": REJECTED_ALL_RED, "detail": f"every one of {measurement.tests} tests failed"}
    if not measurement.failed:
        return {**common, "verdict": SURVIVED, "red": [], "buckets": {}}
    return {**common, "verdict": CAUGHT, "red": list(measurement.failed), "buckets": grouped(config, measurement.failed)}


def queue_of(config: Config, args: argparse.Namespace) -> list[dict[str, str]]:
    done = {record["id"] for record in records_of(config)}
    only = set(args.only.split(",")) if args.only else None
    if only is not None:
        unknown = sorted(only - {mutation["id"] for mutation in config.mutations})
        if unknown:
            raise Refuse(f"--only names no such mutation: {', '.join(unknown)}")
    queue = [m for m in config.mutations if (only is None or m["id"] in only) and (args.force or m["id"] not in done)]
    if args.limit is not None:
        if args.limit < 1:
            raise Refuse("--limit must be at least 1")
        queue = queue[: args.limit]
    return queue


def cmd_run(config: Config, args: argparse.Namespace) -> int:
    refuse_when_marked(config)
    require_ignored_state(config)
    if not config.mutations:
        raise Refuse("the config carries no mutations")
    if args.compile and not config.compile_command:
        raise Refuse("--compile needs a 'compile.command' in the config")
    if not config.baseline_file.exists():
        cmd_baseline(config, args)
    baseline = baseline_of(config)
    refuse_when_dirty(config)

    queue = queue_of(config, args)
    timeout = suite_timeout(config, baseline)
    print(f"{len(queue)} mutation(s) to run, suite timeout {timeout:.0f}s")

    clock = 0.0
    for number, mutation in enumerate(queue, start=1):
        head = f"[{number}/{len(queue)}] {mutation['id']}"
        target = target_of(config, mutation["file"])
        backup = config.state / "backups" / mutation["id"]
        try:
            before, after, clock = apply_mutation(config, mutation, target, backup, clock)
        except Rot as rot:
            append_record(config, {"id": mutation["id"], "file": mutation["file"], "note": mutation["note"], "verdict": ROTTED, "detail": str(rot)})
            print(f"{head}  ROTTED — {rot}", flush=True)
            continue
        print(f"{head}  {mutation['file']}  {before[:8]} -> {after[:8]}", flush=True)

        record: dict[str, Any] = {"id": mutation["id"], "file": mutation["file"], "note": mutation["note"]}
        try:
            compiled = None
            if args.compile:
                compiled = run_process(tuple(expand(argument, config) for argument in config.compile_command), config.compile_cwd, config.compile_timeout_sec, config.state / "logs" / f"{mutation['id']}.compile.log")
                record["compileSeconds"] = round(compiled.seconds, 3)
            if compiled is not None and compiled.code != 0:
                record.update({"verdict": REJECTED_COMPILE, "detail": f"the compile gate exited {compiled.code} — the mutation is not a valid program", "seconds": 0.0})
                launched = True
            else:
                measurement, completed, detail = run_suite(config, mutation["id"], timeout)
                record.update(score(config, baseline, measurement, detail, completed))
                launched = completed.launched
        finally:
            restore(config, mutation, target, backup, before, args.sabotage_restore)

        append_record(config, record)
        print(f"    {record['verdict']}  failed={record.get('failed', '-')}/{record.get('total', '-')}  {record.get('seconds', 0.0):.1f}s  {record.get('detail', '')}", flush=True)
        if not launched:
            raise Refuse(str(record["detail"]))

    left = scope_status(config)
    if left:
        raise abort(config, f"the run finished with the mutable scope dirty:\n{left}")
    print(f"\nrun complete — {len(queue)} mutation(s) this pass, the mutable scope is clean")
    return announce_rot(records_of(config))


def cmd_status(config: Config, args: argparse.Namespace) -> int:
    records = records_of(config)
    for record in records:
        print(f"{record.get('verdict', '?'):<20} {len(record.get('red', [])):>5} red  {record.get('seconds', 0.0):>7.1f}s  {record['id']}  {record.get('note', '')}")
    print(f"{len(records)} recorded")
    return max(announce_rot(records), announce_marker(config))


def cmd_report(config: Config, args: argparse.Namespace) -> int:
    records = records_of(config)
    counts = {verdict: sum(1 for record in records if record.get("verdict") == verdict) for verdict in VERDICTS}
    print("  ".join(f"{verdict}={counts[verdict]}" for verdict in VERDICTS if counts[verdict]) or "nothing recorded")
    exit_code = max(announce_rot(records), announce_marker(config))

    survivors = [record for record in records if record.get("verdict") == SURVIVED]
    if survivors:
        print(f"\nSURVIVED — {len(survivors)} mutation(s) no test caught:")
        for record in survivors:
            print(f"  {record['id']}  {record['file']}  {record.get('note', '')}")

    rejected = [record for record in records if str(record.get("verdict", "")).startswith("REJECTED_")]
    if rejected:
        print(f"\nREJECTED — {len(rejected)} mutation(s) scored nothing:")
        for record in rejected:
            print(f"  {record['id']}  {record['verdict']}  {record.get('detail', '')}")

    union: dict[str, list[str]] = {}
    for record in records:
        for identity in record.get("red", []):
            union.setdefault(identity, []).append(record["id"])
    config.state.mkdir(parents=True, exist_ok=True)
    (config.state / "union.json").write_text(json.dumps(union, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\ntests reddened by at least one accepted mutation:")
    for name, identities in grouped(config, tuple(baseline_of(config)["identities"])).items():
        uncovered = [identity for identity in identities if identity not in union]
        print(f"  {name}: {len(identities) - len(uncovered)}/{len(identities)}")
        if args.uncovered:
            for identity in uncovered:
                print(f"    UNCOVERED  {identity}")
    return exit_code


def cmd_reset(config: Config, args: argparse.Namespace) -> int:
    refuse_when_marked(config)
    for path in (config.results, config.baseline_file, config.state / "union.json"):
        path.unlink(missing_ok=True)
    shutil.rmtree(config.state / "backups", ignore_errors=True)
    print(f"cleared the results and baseline in {config.state}")
    return EXIT_OK


COMMANDS: dict[str, Callable[[Config, argparse.Namespace], int]] = {"baseline": cmd_baseline, "run": cmd_run, "report": cmd_report, "status": cmd_status, "reset": cmd_reset}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mutate.py", description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--mutations", action="append", default=[], type=Path)
    parser.add_argument("--only")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--uncovered", action="store_true")
    parser.add_argument("--sabotage-restore", metavar="ID", help="corrupt one mutation's restore copy, to prove the checksum abort fires")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return COMMANDS[args.command](load_config(args.config, args.mutations), args)
    except Refuse as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_REFUSED
    except Abort as error:
        print(f"ABORTED: {error}", file=sys.stderr)
        return EXIT_ABORTED


if __name__ == "__main__":
    raise SystemExit(main())
