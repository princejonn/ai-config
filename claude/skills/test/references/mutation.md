# Mutation driver

`scripts/mutate.py` applies one mutation, runs the project's suite, restores the file from the copy
taken before the edit and verifies that restore by md5. Results append per mutation id, so an
interrupted campaign costs one run.

## Config

```json
{
  "repo": "..",
  "state": ".tmp/mutate",
  "runner": {
    "command": ["npm", "test", "--", "--reporter=json", "--outputFile={report}"],
    "cwd": "packages/aegis",
    "format": "vitest-json",
    "timeoutSec": null
  },
  "compile": { "command": ["npx", "tsc", "--noEmit", "--incremental", "--tsBuildInfoFile", "{state}/tsc.json"], "cwd": "packages/aegis" },
  "mutable": ["packages/aegis/src/*"],
  "buckets": { "feature": ["*.feature"], "unit": ["*.test.ts"] },
  "mutations": [
    { "id": "alg-fallback", "file": "packages/aegis/src/sign.ts", "old": "alg ?? \"ES256\"", "new": "alg ?? \"HS256\"", "note": "the fallback arm" }
  ]
}
```

- Paths are relative: `repo` to the config file, everything else to `repo`. `repo` defaults to the
  config file's git toplevel, `state` to `<repo>/.tmp/mutate`, which git must ignore.
- `{state}` and `{repo}` expand in any command word, `{report}` in the runner's. The runner is free
  — `sh -lc "..."` where a shell is wanted — as long as it leaves a report at `{report}`.
- `format` is `vitest-json` (vitest or jest `--reporter=json`) or `junit` (pytest `--junitxml`, and
  any runner with a JUnit reporter).
- `mutable` is required and every mutation path must match one; patterns are `fnmatch` over the
  repo-relative POSIX path, where `*` spans `/`. Test material is refused on top of that —
  `protected` replaces the default list where a language keeps tests beside the code.
- `timeoutSec` defaults to ten times the measured baseline, floor 60s; the runner is killed by
  process group, so its workers go with it.
- `--mutations <file.json>` appends a JSON array of mutations, repeatable, for a campaign whose
  spec outgrows one file.

## Commands

| | |
|---|---|
| `baseline` | run the suite unmutated and record the file count, test count, wall time and every test identity; `--force` re-measures |
| `run` | `--only id,id`, `--limit N`, `--force` to re-run recorded ids, `--compile` to gate on the compile command first |
| `report` | verdict counts, rot, survivors, rejections, and per bucket the tests some mutation reddened; `--uncovered` lists the rest |
| `status` | one line per recorded verdict |
| `reset` | drop the results and the baseline |

Exit: 0 clean, 1 rot or an abort marker, 2 refused, 3 aborted mid-run.

| verdict | meaning |
|---|---|
| `CAUGHT` | some tests went red — `red` names them, `buckets` groups them |
| `SURVIVED` | no test went red |
| `REJECTED_COMPILE` | the compile gate refused it |
| `REJECTED_COLLECTION` | the runner collected a different number of files or tests than the baseline |
| `REJECTED_ALL_RED` | every test failed |
| `REJECTED_NO_RESULT` / `REJECTED_TIMEOUT` | no report, or the suite outran its timeout |
| `ROTTED` | the anchor did not occur exactly once, or the file is gone — nothing was written |

A restore whose md5 does not match, or a scope left dirty, writes `<state>/ABORT` and stops
everything; every command refuses until it is read and deleted by hand. `--sabotage-restore <id>`
corrupts one copy on purpose, which is how that abort is shown to fire.

## Isolation

Concurrency buys nothing — several suites at once measured 1.05x on 16 cores, because one vitest run
already saturates them. A worktree is for isolation, so that a campaign and ordinary work do not
share a tree.

A fresh `git worktree` cannot run a JS workspace suite at all: packages symlink to source and every
`dist/` is gitignored, so it dies with `ERR_MODULE_NOT_FOUND`. Seeding takes about 8s with APFS
clonefile and no network:

```bash
git worktree add --detach <path> <sha>
cp -Rc node_modules <path>/
for d in packages/*/dist; do cp -Rc "$d" "<path>/$d"; done
```

The relative workspace symlinks then resolve inside the worktree.

## Costs

A TypeScript compile gate runs in about 2s per mutation with `--incremental --tsBuildInfoFile
{state}/…`, against about 90s without.

The driver stamps each mutated file with an mtime later than the last, because a cache keyed on
whole-second mtimes — CPython's `__pycache__` among them — otherwise serves the previous mutation's
build to a suite that fits several mutations into one second.
