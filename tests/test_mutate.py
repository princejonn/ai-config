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
REFERENCE = REPO / "claude" / "skills" / "test" / "references" / "mutation.md"

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

EXTRA_TESTS = '''import unittest

from src.calc import clamp


class BoundaryTest(unittest.TestCase):
    def test_a_value_on_the_low_bound_is_returned_unchanged(self):
        self.assertEqual(clamp(0, 0, 10), 0)
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

    def test_the_baseline_is_measured_from_the_unmutated_tree(self):
        done = self.drive("baseline")
        self.assertEqual(done.returncode, 0, done.stderr)
        baseline = json.loads((self.state / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual((baseline["files"], baseline["tests"]), (2, 5))
        self.assertIn("baseline: 2 file(s), 5 test(s)", done.stdout)

    def test_a_test_added_after_the_baseline_does_not_reject_a_mutation_once_the_baseline_is_remeasured(self):
        self.assertEqual(self.drive("baseline").returncode, 0)
        self.write(self.project / "tests" / "test_boundary.py", EXTRA_TESTS)
        self.assertEqual(self.drive("baseline", "--force").returncode, 0)
        baseline = json.loads((self.state / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual((baseline["files"], baseline["tests"]), (3, 6))
        self.drive("run", "--only", CAUGHT_BY_ONE["id"])
        self.assertEqual(self.verdicts()[CAUGHT_BY_ONE["id"]], "CAUGHT")

    def test_a_mutation_the_suite_catches_records_the_tests_that_went_red(self):
        done = self.drive("run", "--only", CAUGHT_BY_ONE["id"])
        self.assertEqual(done.returncode, 0, done.stderr)
        record = self.records()[0]
        self.assertEqual(record["verdict"], "CAUGHT")
        self.assertEqual(record["red"], ["tests/test_clamp.py :: tests.test_clamp.ClampTest.test_below_the_low_bound_returns_the_low_bound"])

    def test_a_mutation_no_test_catches_is_recorded_survived(self):
        self.drive("run", "--only", SURVIVES["id"])
        self.assertEqual(self.verdicts()[SURVIVES["id"]], "SURVIVED")

    def test_failing_tests_are_grouped_by_the_configured_path_patterns(self):
        self.drive("run", "--only", CAUGHT_IN_LABEL["id"])
        self.assertEqual(sorted(self.records()[0]["buckets"]), ["label"])

    def test_a_mutation_that_reddens_every_test_is_rejected_rather_than_scored(self):
        self.drive("run", "--only", ALL_RED["id"])
        record = self.records()[0]
        self.assertEqual(record["verdict"], "REJECTED_ALL_RED")
        self.assertNotIn("red", record)

    def test_a_mutation_that_changes_what_the_runner_collects_is_rejected_rather_than_scored(self):
        self.drive("run", "--only", UNPARSEABLE["id"])
        record = self.records()[0]
        self.assertEqual(record["verdict"], "REJECTED_COLLECTION")
        self.assertNotIn("red", record)

    def test_a_mutation_the_compile_gate_refuses_is_rejected_rather_than_scored(self):
        done = self.drive("run", "--only", UNPARSEABLE["id"], "--compile")
        record = self.records()[0]
        self.assertEqual(record["verdict"], "REJECTED_COMPILE")
        self.assertNotIn("red", record)
        self.assertIn("REJECTED_COMPILE", done.stdout)

    def test_a_mutation_the_compile_gate_accepts_is_scored(self):
        self.drive("run", "--only", CAUGHT_BY_ONE["id"], "--compile")
        self.assertEqual(self.verdicts()[CAUGHT_BY_ONE["id"]], "CAUGHT")

    def test_mutations_of_one_size_inside_one_second_are_each_run_against_their_own_source(self):
        self.config = self.configure([CAUGHT_BY_ONE, SURVIVES, CAUGHT_IN_LABEL])
        self.assertEqual(self.drive("run").returncode, 0)
        self.assertEqual(self.verdicts(), {CAUGHT_BY_ONE["id"]: "CAUGHT", SURVIVES["id"]: "SURVIVED", CAUGHT_IN_LABEL["id"]: "CAUGHT"})
        self.assertEqual([len(record.get("red", [])) for record in self.records()], [1, 0, 2])

    def test_the_source_is_restored_byte_for_byte_after_every_mutation(self):
        before = self.source.read_bytes()
        done = self.drive("run")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIn("the mutable scope is clean", done.stdout)

    def test_an_id_already_recorded_is_left_alone_until_force(self):
        self.drive("run", "--only", CAUGHT_BY_ONE["id"])
        again = self.drive("run", "--only", CAUGHT_BY_ONE["id"])
        self.assertIn("0 mutation(s) to run", again.stdout)
        self.assertEqual(len(self.records()), 1)
        self.drive("run", "--only", CAUGHT_BY_ONE["id"], "--force")
        self.assertEqual(len(self.records()), 2)

    def test_the_suite_timeout_is_ten_times_the_measured_baseline_above_its_floor(self):
        self.assertEqual(self.drive("baseline").returncode, 0)
        baseline = json.loads((self.state / "baseline.json").read_text(encoding="utf-8"))
        baseline["seconds"] = 30.0
        self.write(self.state / "baseline.json", json.dumps(baseline))
        self.assertIn("suite timeout 300s", self.drive("run", "--only", SURVIVES["id"]).stdout)

    def test_the_suite_timeout_does_not_fall_below_its_floor(self):
        self.assertIn("suite timeout 60s", self.drive("run", "--only", SURVIVES["id"]).stdout)


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

    def test_an_anchor_that_occurs_nowhere_is_recorded_rotted_and_the_file_is_left_alone(self):
        before = self.source.read_bytes()
        self.drive("run", "--only", ROTTED_ABSENT["id"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.verdicts()[ROTTED_ABSENT["id"]], "ROTTED")

    def test_a_mutation_naming_a_file_that_is_not_there_is_recorded_rotted(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "id": "gone", "file": "src/missing.py"}])
        done = self.drive("run")
        self.assertEqual(done.returncode, 1)
        self.assertIn("ROTTED — no such file: src/missing.py", done.stdout)

    def test_rot_leaves_run_report_and_status_naming_it_and_exiting_non_zero(self):
        run = self.drive("run", "--only", f"{ROTTED_TWICE['id']},{CAUGHT_BY_ONE['id']}")
        self.assertEqual(run.returncode, 1)
        for command in ("report", "status"):
            with self.subTest(command=command):
                done = self.drive(command)
                self.assertEqual(done.returncode, 1)
                self.assertIn("ROTTED — 1 mutation(s) never ran", done.stdout)
                self.assertIn(ROTTED_TWICE["id"], done.stdout)

    def test_rot_recorded_in_an_earlier_pass_reddens_every_later_run(self):
        self.drive("run", "--only", ROTTED_TWICE["id"])
        later = self.drive("run", "--only", CAUGHT_BY_ONE["id"])
        self.assertEqual(later.returncode, 1)
        self.assertIn(ROTTED_TWICE["id"], later.stdout)

    def test_a_run_of_sound_mutations_alone_exits_zero(self):
        self.assertEqual(self.drive("run", "--only", CAUGHT_BY_ONE["id"]).returncode, 0)
        self.assertEqual(self.drive("report").returncode, 0)


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

    def test_the_marker_makes_report_and_status_exit_non_zero(self):
        self.drive("run", "--sabotage-restore", CAUGHT_BY_ONE["id"])
        for command in ("report", "status"):
            with self.subTest(command=command):
                done = self.drive(command)
                self.assertEqual(done.returncode, 1)
                self.assertIn("ABORTED", done.stdout)

    def test_no_verdict_is_recorded_for_the_mutation_whose_restore_failed_nor_for_the_one_after_it(self):
        self.drive("run", "--sabotage-restore", CAUGHT_BY_ONE["id"])
        self.assertEqual([record["id"] for record in self.records()], [])


class RefusalTest(DriverTestCase):
    def refusal(self, *arguments, config=None):
        done = self.drive(*arguments, config=config)
        self.assertEqual(done.returncode, 2, done.stdout)
        return done.stderr

    def test_a_dirty_mutable_scope_is_refused_before_anything_is_written(self):
        self.config = self.configure([CAUGHT_BY_ONE])
        self.write(self.source, SOURCE + "\n# edited\n")
        self.assertIn("the mutable scope is dirty", self.refusal("run"))

    def test_a_state_directory_git_does_not_ignore_is_refused(self):
        self.config = self.configure([CAUGHT_BY_ONE], state="state")
        self.assertIn("is not ignored by git", self.refusal("run"))

    def test_a_file_outside_the_mutable_patterns_is_refused(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "file": "runtests.py", "old": "ROOT = Path", "new": "ROOT = None or Path"}])
        self.assertIn("matches no 'mutable' pattern", self.refusal("run"))

    def test_test_material_is_refused_even_where_a_mutable_pattern_admits_it(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "file": "tests/test_clamp.py", "old": "clamp(-1, 0, 10), 0", "new": "clamp(-1, 0, 10), 1"}], mutable=["src/*", "tests/*"])
        self.assertIn("is test material (protected pattern", self.refusal("run"))

    def test_a_path_escaping_the_repository_is_refused(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "file": "../outside.py"}], mutable=["*"])
        self.assertIn("resolves outside the repository", self.refusal("run"))

    def test_an_absolute_mutation_path_is_refused(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "file": str(self.source)}], mutable=["*"])
        self.assertIn("relative to the repository", self.refusal("run"))

    def test_two_mutations_sharing_an_id_are_refused(self):
        self.config = self.configure([CAUGHT_BY_ONE, {**SURVIVES, "id": CAUGHT_BY_ONE["id"]}])
        self.assertIn("duplicate mutation id", self.refusal("run"))

    def test_a_mutation_replacing_its_anchor_with_itself_is_refused(self):
        self.config = self.configure([{**CAUGHT_BY_ONE, "new": CAUGHT_BY_ONE["old"]}])
        self.assertIn("replaces the anchor with itself", self.refusal("run"))

    def test_a_red_baseline_is_refused(self):
        self.config = self.configure([CAUGHT_BY_ONE])
        self.write(self.source, SOURCE.replace('FALLBACK = "anon"', 'FALLBACK = "other"'))
        subprocess.run(["git", "-C", str(self.project), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "red"], check=True, capture_output=True)
        self.assertIn("the baseline suite is not green", self.refusal("baseline"))

    def test_a_runner_that_cannot_be_started_is_refused_rather_than_scored(self):
        self.config = self.configure([CAUGHT_BY_ONE], runner={"command": ["./no-such-runner", "{report}"], "format": "junit"})
        self.assertIn("the runner could not be started", self.refusal("baseline"))

    def test_a_compile_run_without_a_compile_command_is_refused(self):
        self.config = self.configure([CAUGHT_BY_ONE], compile={})
        self.assertIn("--compile needs a 'compile.command'", self.refusal("run", "--compile"))

    def test_only_naming_an_unknown_mutation_is_refused(self):
        self.config = self.configure([CAUGHT_BY_ONE])
        self.assertIn("--only names no such mutation: ghost", self.refusal("run", "--only", "ghost"))

    def test_an_unknown_report_format_is_refused(self):
        self.config = self.configure([CAUGHT_BY_ONE], runner={"command": ["true"], "format": "tap"})
        self.assertIn("runner.format must be one of", self.refusal("run"))

    def test_a_config_without_mutations_is_refused(self):
        self.config = self.configure([])
        self.assertIn("carries no mutations", self.refusal("run"))


class ReportTest(DriverTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.configure([CAUGHT_BY_ONE, SURVIVES, CAUGHT_IN_LABEL])
        self.assertEqual(self.drive("run").returncode, 0)

    def test_report_names_every_survivor_with_its_note(self):
        done = self.drive("report")
        self.assertIn("SURVIVED — 1 mutation(s) no test caught:", done.stdout)
        self.assertIn(SURVIVES["note"], done.stdout)

    def test_report_counts_the_tests_reddened_per_bucket(self):
        done = self.drive("report")
        self.assertIn("clamp: 1/3", done.stdout)
        self.assertIn("label: 2/2", done.stdout)

    def test_report_lists_the_tests_no_mutation_reddened_on_request(self):
        done = self.drive("report", "--uncovered")
        self.assertIn("UNCOVERED  tests/test_clamp.py :: tests.test_clamp.ClampTest.test_inside_the_bounds_returns_the_value", done.stdout)

    def test_the_union_records_which_mutations_reddened_each_test(self):
        self.drive("report")
        union = json.loads((self.state / "union.json").read_text(encoding="utf-8"))
        self.assertEqual(union["tests/test_clamp.py :: tests.test_clamp.ClampTest.test_below_the_low_bound_returns_the_low_bound"], [CAUGHT_BY_ONE["id"]])

    def test_reset_clears_the_results_and_the_baseline(self):
        self.assertEqual(self.drive("reset").returncode, 0)
        self.assertFalse((self.state / "results.jsonl").exists())
        self.assertFalse((self.state / "baseline.json").exists())


class ParserTest(unittest.TestCase):
    def test_junit_reads_the_file_the_name_and_the_failure_of_every_case(self):
        text = '<testsuites><testsuite name="s"><testcase file="a.py" name="one"/><testcase file="a.py" name="two"><failure message="x"/></testcase><testcase file="b.py" name="three"><error message="y"/></testcase></testsuite></testsuites>'
        cases = mutate.parse_junit(text, Path("/repo"))
        self.assertEqual([(case.file, case.name, case.failed) for case in cases], [("a.py", "one", False), ("a.py", "two", True), ("b.py", "three", True)])

    def test_junit_falls_back_from_the_file_attribute_to_the_classname(self):
        cases = mutate.parse_junit('<testsuite name="s"><testcase classname="pkg.mod" name="one"/></testsuite>', Path("/repo"))
        self.assertEqual(cases[0].file, "pkg.mod")

    def test_vitest_json_reads_the_suite_path_and_the_full_name_of_every_assertion(self):
        text = json.dumps({"testResults": [{"name": "/repo/src/a.test.ts", "assertionResults": [{"fullName": "one", "status": "passed"}, {"fullName": "two", "status": "failed"}]}]})
        cases = mutate.parse_vitest_json(text, Path("/repo"))
        self.assertEqual([(case.file, case.name, case.failed) for case in cases], [("src/a.test.ts", "one", False), ("src/a.test.ts", "two", True)])

    def test_a_measurement_counts_the_distinct_files_and_every_case(self):
        measurement = mutate.measured([mutate.Case("a", "one", False), mutate.Case("a", "two", True), mutate.Case("b", "three", False)])
        self.assertEqual((measurement.files, measurement.tests, measurement.failed), (2, 3, ("a :: two",)))


class SourceTest(unittest.TestCase):
    def test_the_driver_calls_no_git_subcommand_that_could_restore_a_file(self):
        self.assertEqual(set(GIT_SUBCOMMAND.findall(DRIVER.read_text(encoding="utf-8"))), GIT_SUBCOMMANDS_USED)

    def test_the_reference_names_every_verdict_the_driver_records(self):
        for verdict in mutate.VERDICTS:
            with self.subTest(verdict=verdict):
                self.assertIn(f"`{verdict}`", REFERENCE.read_text(encoding="utf-8"))

    def test_the_reference_names_every_command_the_driver_takes(self):
        for command in mutate.COMMANDS:
            with self.subTest(command=command):
                self.assertIn(f"| `{command}` |", REFERENCE.read_text(encoding="utf-8"))

    def test_the_reference_names_every_report_format_the_driver_parses(self):
        for name in mutate.PARSERS:
            with self.subTest(format=name):
                self.assertIn(f"`{name}`", REFERENCE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
