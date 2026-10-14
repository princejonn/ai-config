import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "claude" / "skills" / "test" / "scripts" / "mutate.py"

SPEC = importlib.util.spec_from_file_location("mutate", DRIVER)
mutate = importlib.util.module_from_spec(SPEC)
sys.modules["mutate"] = mutate
SPEC.loader.exec_module(mutate)

GIT_SUBCOMMAND = re.compile(r"\bgit\((?:here|config\.repo|repo), \"([a-z-]+)\"")
GIT_SUBCOMMANDS_USED = {"rev-parse", "status", "check-ignore"}

SOURCE = '''FALLBACK = "anon"


def _checked(value):
    if value is None:
        raise ValueError("missing value")
    return value


def clamp(value, low, high):
    value = _checked(value)
    if value < low:
        return low
    if value > high:
        return high
    return value


def label(name):
    return _checked(name) or FALLBACK
'''

CLAMP_TESTS = '''import unittest

from src.calc import clamp


class ClampTest(unittest.TestCase):
    def test_below_the_low_bound_returns_the_low_bound(self):
        self.assertEqual(clamp(-1, 0, 10), 0)

    def test_above_the_high_bound_returns_the_high_bound(self):
        self.assertEqual(clamp(11, 0, 10), 10)

    def test_inside_the_bounds_returns_the_value(self):
        self.assertEqual(clamp(5, 0, 10), 5)
'''

LABEL_TESTS = '''import unittest

from src.calc import label


class LabelTest(unittest.TestCase):
    def test_an_empty_name_becomes_the_fallback(self):
        self.assertEqual(label(""), "anon")

    def test_a_given_name_is_returned_as_it_came(self):
        self.assertEqual(label("widget"), "widget")
'''

HARNESS = '''import os
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def source_of(test):
    module = sys.modules.get(type(test).__module__)
    path = getattr(module, "__file__", "") or ""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return type(test).__module__


def main():
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    tests = list(flatten(suite))
    with open(os.devnull, "w") as quiet:
        result = unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
    failed = {test.id() for test, _ in result.failures + result.errors}
    root = ElementTree.Element("testsuites")
    element = ElementTree.SubElement(root, "testsuite", {"name": "unittest", "tests": str(len(tests)), "failures": str(len(failed))})
    for test in tests:
        where = source_of(test)
        case = ElementTree.SubElement(element, "testcase", {"file": where, "classname": where, "name": test.id()})
        if test.id() in failed:
            ElementTree.SubElement(case, "failure", {"message": "failed"})
    ElementTree.ElementTree(root).write(sys.argv[1], encoding="unicode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

CAUGHT_BY_ONE = {"id": "low-bound-returns-high", "file": "src/calc.py", "old": "    if value < low:\n        return low", "new": "    if value < low:\n        return high", "note": "clamp returns the wrong bound"}
SURVIVES = {"id": "low-bound-comparison", "file": "src/calc.py", "old": "if value < low:", "new": "if value <= low:", "note": "no test stands on the low boundary"}
CAUGHT_IN_LABEL = {"id": "fallback-conjunction", "file": "src/calc.py", "old": "return _checked(name) or FALLBACK", "new": "return _checked(name) and FALLBACK", "note": "label folds every name to the fallback"}
ALL_RED = {"id": "checked-always-raises", "file": "src/calc.py", "old": '        raise ValueError("missing value")\n    return value', "new": '        raise ValueError("missing value")\n    raise ValueError("boom")', "note": "every call raises"}
UNPARSEABLE = {"id": "trailing-operator", "file": "src/calc.py", "old": "    if value > high:\n        return high\n    return value", "new": "    if value > high:\n        return high\n    return value +", "note": "not a valid program"}
ROTTED_TWICE = {"id": "anchor-twice", "file": "src/calc.py", "old": "    return value\n", "new": "    return low\n", "note": "the anchor occurs twice"}
ROTTED_ABSENT = {"id": "anchor-absent", "file": "src/calc.py", "old": "return maximum", "new": "return minimum", "note": "the anchor is gone"}


class DriverTestCase(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="ai-config-mutate.")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.project = self.work / "project"
        (self.project / "src").mkdir(parents=True)
        (self.project / "tests").mkdir()
        self.source = self.project / "src" / "calc.py"
        self.write(self.source, SOURCE)
        self.write(self.project / "tests" / "__init__.py", "")
        self.write(self.project / "tests" / "test_clamp.py", CLAMP_TESTS)
        self.write(self.project / "tests" / "test_label.py", LABEL_TESTS)
        self.write(self.project / "runtests.py", HARNESS)
        self.write(self.project / ".gitignore", ".tmp/\n__pycache__/\n")
        self.commit()
        self.state = self.project / ".tmp" / "mutate"

    def write(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")

    def commit(self) -> None:
        for arguments in (["init", "-q", "-b", "main"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"]):
            done = subprocess.run(["git", "-C", str(self.project), *arguments], capture_output=True, text=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)

    def configure(self, mutations, **overrides) -> Path:
        document = {
            "repo": str(self.project),
            "runner": {"command": [sys.executable, "runtests.py", "{report}"], "format": "junit"},
            "compile": {"command": [sys.executable, "-m", "py_compile", "src/calc.py"]},
            "mutable": ["src/*"],
            "buckets": {"clamp": ["tests/test_clamp.py"], "label": ["tests/test_label.py"]},
            "mutations": mutations,
        }
        document.update(overrides)
        path = self.work / "mutate.json"
        self.write(path, json.dumps(document, indent=2))
        return path

    def drive(self, *arguments, config=None):
        return subprocess.run([sys.executable, str(DRIVER), *arguments, "--config", str(config or self.config)], capture_output=True, text=True, check=False)

    def records(self):
        results = self.state / "results.jsonl"
        if not results.exists():
            return []
        return [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines() if line.strip()]

    def verdicts(self):
        return {record["id"]: record["verdict"] for record in self.records()}


class RunTest(DriverTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.configure([CAUGHT_BY_ONE, SURVIVES, CAUGHT_IN_LABEL, ALL_RED, UNPARSEABLE, ROTTED_TWICE, ROTTED_ABSENT])

    def test_a_mutation_the_suite_catches_records_the_tests_that_went_red(self):
        done = self.drive("run", "--only", CAUGHT_BY_ONE["id"])
        self.assertEqual(done.returncode, 0, done.stderr)
        record = self.records()[0]
        self.assertEqual(record["verdict"], "CAUGHT")
        self.assertEqual(record["red"], ["tests/test_clamp.py :: tests.test_clamp.ClampTest.test_below_the_low_bound_returns_the_low_bound"])

    def test_a_mutation_no_test_catches_is_recorded_survived(self):
        self.drive("run", "--only", SURVIVES["id"])
        self.assertEqual(self.verdicts()[SURVIVES["id"]], "SURVIVED")

    def test_a_mutation_that_reddens_every_test_is_rejected_rather_than_scored(self):
        self.drive("run", "--only", ALL_RED["id"])
        record = self.records()[0]
        self.assertEqual(record["verdict"], "REJECTED_ALL_RED")
        self.assertNotIn("red", record)

    def test_a_mutation_the_compile_gate_refuses_is_rejected_rather_than_scored(self):
        done = self.drive("run", "--only", UNPARSEABLE["id"], "--compile")
        record = self.records()[0]
        self.assertEqual(record["verdict"], "REJECTED_COMPILE")
        self.assertNotIn("red", record)
        self.assertIn("REJECTED_COMPILE", done.stdout)

    def test_the_source_is_restored_byte_for_byte_after_every_mutation(self):
        before = self.source.read_bytes()
        done = self.drive("run")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn("the mutable scope is clean", done.stdout)


class RotTest(DriverTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.configure([ROTTED_TWICE, ROTTED_ABSENT, CAUGHT_BY_ONE])

    def test_an_anchor_that_occurs_twice_is_recorded_rotted_and_the_file_is_left_alone(self):
        before = self.source.read_bytes()
        done = self.drive("run", "--only", ROTTED_TWICE["id"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.verdicts()[ROTTED_TWICE["id"]], "ROTTED")
        self.assertIn("the anchor occurs 2x in src/calc.py", done.stdout)

    def test_rot_leaves_run_report_and_status_naming_it_and_exiting_non_zero(self):
        run = self.drive("run", "--only", f"{ROTTED_TWICE['id']},{CAUGHT_BY_ONE['id']}")
        self.assertEqual(run.returncode, 1)
        for command in ("report", "status"):
            with self.subTest(command=command):
                done = self.drive(command)
                self.assertEqual(done.returncode, 1)
                self.assertIn("ROTTED — 1 mutation(s) never ran", done.stdout)
                self.assertIn(ROTTED_TWICE["id"], done.stdout)


class AbortTest(DriverTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.configure([CAUGHT_BY_ONE, SURVIVES])
        self.marker = self.state / "ABORT"

    def test_a_restore_that_does_not_reproduce_the_file_aborts_and_leaves_a_marker(self):
        done = self.drive("run", "--sabotage-restore", CAUGHT_BY_ONE["id"])
        self.assertEqual(done.returncode, 3)
        self.assertIn("ABORTED:", done.stderr)
        self.assertIn(f"restoring src/calc.py for mutation {CAUGHT_BY_ONE['id']}", done.stderr)
        self.assertTrue(self.marker.is_file())

    def test_the_marker_refuses_every_further_run_until_it_is_deleted_by_hand(self):
        self.drive("run", "--sabotage-restore", CAUGHT_BY_ONE["id"])
        for command in ("run", "baseline", "reset"):
            with self.subTest(command=command):
                done = self.drive(command)
                self.assertEqual(done.returncode, 2)
                self.assertIn("a previous run aborted", done.stderr)
        self.marker.unlink()
        self.assertEqual(self.drive("reset").returncode, 0)


class RefusalTest(DriverTestCase):
    def refusal(self, *arguments, config=None):
        done = self.drive(*arguments, config=config)
        self.assertEqual(done.returncode, 2, done.stdout)
        return done.stderr

    def test_a_dirty_mutable_scope_is_refused_before_anything_is_written(self):
        self.config = self.configure([CAUGHT_BY_ONE])
        self.write(self.source, SOURCE + "\n# edited\n")
        self.assertIn("the mutable scope is dirty", self.refusal("run"))

    def test_test_material_is_refused_even_where_a_mutable_pattern_admits_it(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "file": "tests/test_clamp.py", "old": "clamp(-1, 0, 10), 0", "new": "clamp(-1, 0, 10), 1"}], mutable=["src/*", "tests/*"])
        self.assertIn("is test material (protected pattern", self.refusal("run"))

    def test_a_path_escaping_the_repository_is_refused(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "file": "../outside.py"}], mutable=["*"])
        self.assertIn("resolves outside the repository", self.refusal("run"))


class ParserTest(unittest.TestCase):
    def test_vitest_json_reads_the_suite_path_and_the_full_name_of_every_assertion(self):
        text = json.dumps({"testResults": [{"name": "/repo/src/a.test.ts", "assertionResults": [{"fullName": "one", "status": "passed"}, {"fullName": "two", "status": "failed"}]}]})
        cases = mutate.parse_vitest_json(text, Path("/repo"))
        self.assertEqual([(case.file, case.name, case.failed) for case in cases], [("src/a.test.ts", "one", False), ("src/a.test.ts", "two", True)])


class SourceTest(unittest.TestCase):
    def test_the_driver_calls_no_git_subcommand_that_could_restore_a_file(self):
        self.assertEqual(set(GIT_SUBCOMMAND.findall(DRIVER.read_text(encoding="utf-8"))), GIT_SUBCOMMANDS_USED)


if __name__ == "__main__":
    unittest.main()
