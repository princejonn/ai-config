import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "write-guard.py")
SPEC = importlib.util.spec_from_file_location("write_guard", HOOK_PATH)
write_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(write_guard)

CWD = "/Users/jonn/Projects/lindorm/lindorm-monorepo"
PACKAGE_JSON = '{\n  "name": "x",\n  "version": "0.1.0",\n  "private": true,\n  "engines": {\n    "node": ">=24",\n    "version": "1"\n  },\n  "dependencies": {\n    "a": "0.1.0"\n  }\n}\n'


def call(tool_name, tool_input, cwd=CWD):
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "cwd": cwd, "tool_input": tool_input}


def decision(result):
    return None if result is None else result["hookSpecificOutput"]["permissionDecision"]


class PackageJsonCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "package.json")

    def write_disk(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def edit(self, old, new, replace_all=False):
        tool_input = {"file_path": self.path, "old_string": old, "new_string": new}
        if replace_all:
            tool_input["replace_all"] = True
        return decision(write_guard.evaluate(call("Edit", tool_input)))

    def multi_edit(self, edits):
        return decision(write_guard.evaluate(call("MultiEdit", {"file_path": self.path, "edits": edits})))


class EnvFileTests(unittest.TestCase):
    def test_denies_env_and_env_variants(self):
        for name in (".env", ".env.local", ".env.production"):
            with self.subTest(name=name):
                result = write_guard.evaluate(call("Write", {"file_path": f"{CWD}/{name}", "content": "A=1"}))
                self.assertEqual(decision(result), "deny")

    def test_permits_env_example(self):
        self.assertIsNone(write_guard.evaluate(call("Edit", {"file_path": f"{CWD}/.env.example", "old_string": "a", "new_string": "b"})))

    def test_relative_path_resolves_against_cwd(self):
        self.assertEqual(decision(write_guard.evaluate(call("Write", {"file_path": ".env", "content": ""}))), "deny")

    def test_notebook_path_is_honoured(self):
        result = write_guard.evaluate(call("NotebookEdit", {"notebook_path": f"{CWD}/dist/nb.ipynb", "new_source": ""}))
        self.assertEqual(decision(result), "deny")
        self.assertIsNone(write_guard.evaluate(call("NotebookEdit", {"notebook_path": f"{CWD}/docs/nb.ipynb", "new_source": ""})))


class ReadOnlySegmentTests(unittest.TestCase):
    def test_denies_generated_and_vendored_segments(self):
        for segment in ("node_modules", "dist", ".git", "coverage", "build"):
            with self.subTest(segment=segment):
                result = write_guard.evaluate(call("Edit", {"file_path": f"{CWD}/packages/x/{segment}/index.js", "old_string": "a", "new_string": "b"}))
                self.assertEqual(decision(result), "deny")

    def test_segment_match_is_exact_not_substring(self):
        self.assertIsNone(write_guard.evaluate(call("Edit", {"file_path": f"{CWD}/packages/x/src/builder.ts", "old_string": "a", "new_string": "b"})))
        self.assertIsNone(write_guard.evaluate(call("Write", {"file_path": f"{CWD}/packages/x/src/build.ts", "content": ""})))

    def test_permits_source_files(self):
        self.assertIsNone(write_guard.evaluate(call("Write", {"file_path": f"{CWD}/packages/aegis/src/a.ts", "content": ""})))

    def test_dot_dot_traversal_into_a_read_only_segment_is_denied(self):
        result = write_guard.evaluate(call("Edit", {"file_path": f"{CWD}/packages/x/src/../dist/index.js", "old_string": "a", "new_string": "b"}))
        self.assertEqual(decision(result), "deny")


class SymlinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.real = os.path.join(self.tmp.name, "pkg", "node_modules", "dep")
        os.makedirs(self.real)
        self.link = os.path.join(self.tmp.name, "alias")
        os.symlink(os.path.join(self.tmp.name, "pkg", "node_modules"), self.link)

    def test_symlink_into_a_read_only_directory_is_denied(self):
        result = write_guard.evaluate(call("Edit", {"file_path": f"{self.link}/dep/index.js", "old_string": "a", "new_string": "b"}))
        self.assertEqual(decision(result), "deny")

    def test_symlink_to_a_source_directory_is_permitted(self):
        source = os.path.join(self.tmp.name, "src")
        os.makedirs(source)
        link = os.path.join(self.tmp.name, "dist")
        os.symlink(source, link)
        self.assertIsNone(write_guard.evaluate(call("Edit", {"file_path": f"{link}/a.ts", "old_string": "a", "new_string": "b"})))


class PackageJsonEditTests(PackageJsonCase):
    def setUp(self):
        super().setUp()
        self.write_disk(PACKAGE_JSON)

    def test_denies_edit_touching_version_line(self):
        self.assertEqual(self.edit('"version": "0.1.0"', '"version": "0.2.0"'), "deny")

    def test_denies_edit_touching_only_the_version_value(self):
        self.assertEqual(self.edit('"0.1.0"', '"0.2.0"'), "deny")

    def test_denies_edit_introducing_version_key(self):
        self.write_disk('{\n  "name": "x"\n}\n')
        self.assertEqual(self.edit('"name": "x"', '"name": "x",\n  "version" : "1.0.0"'), "deny")

    def test_denies_edit_removing_version_key(self):
        self.assertEqual(self.edit('  "version": "0.1.0",\n', ""), "deny")

    def test_denies_multiedit_with_version_in_any_edit(self):
        edits = [{"old_string": '"private": true', "new_string": '"private": false'}, {"old_string": '"version": "0.1.0"', "new_string": '"version": "0.1.1"'}]
        self.assertEqual(self.multi_edit(edits), "deny")

    def test_denies_edit_changing_version_among_other_lines(self):
        old = '  "name": "x",\n  "version": "0.1.0",\n  "private": true'
        new = '  "name": "x",\n  "version": "0.1.1",\n  "private": true'
        self.assertEqual(self.edit(old, new), "deny")

    def test_denies_version_change_that_only_moves_the_comma(self):
        self.assertEqual(self.edit('"version": "0.1.0",', '"version": "0.2.0",'), "deny")

    def test_replace_all_reaching_the_top_level_version_is_denied(self):
        self.write_disk('{\n  "dependencies": {\n    "a": "0.1.0"\n  },\n  "version": "0.1.0"\n}\n')
        self.assertEqual(self.edit('"0.1.0"', '"0.2.0"', replace_all=True), "deny")
        self.assertIsNone(self.edit('"0.1.0"', '"0.2.0"'))

    def test_permits_edit_of_other_fields(self):
        self.assertIsNone(self.edit('"private": true', '"private": false'))
        self.assertIsNone(self.multi_edit([{"old_string": '"name": "x"', "new_string": '"name": "y"'}]))

    def test_permits_dependency_range_matching_the_version_value(self):
        self.assertIsNone(self.edit('"a": "0.1.0"', '"a": "0.2.0"'))

    def test_permits_edit_spanning_an_unchanged_version_line(self):
        old = '  "name": "x",\n  "version": "0.1.0",\n  "private": true'
        new = '  "name": "y",\n  "version": "0.1.0",\n  "private": false'
        self.assertIsNone(self.edit(old, new))
        self.assertIsNone(self.multi_edit([{"old_string": old, "new_string": new}]))

    def test_nested_version_keys_are_ignored(self):
        self.assertIsNone(self.edit('"version": "1"', '"version": "2"'))
        self.assertIsNone(self.edit('    "node": ">=24",\n    "version": "1"\n', '    "node": ">=24"\n'))

    def test_version_key_in_other_files_is_ignored(self):
        self.assertIsNone(write_guard.evaluate(call("Edit", {"file_path": f"{CWD}/src/x.ts", "old_string": '"version": 1', "new_string": '"version": 2'})))

    def test_fails_open_when_old_string_is_absent(self):
        self.assertIsNone(self.edit('"version": "9.9.9"', '"version": "0.2.0"'))

    def test_fails_open_when_file_is_missing(self):
        os.remove(self.path)
        self.assertIsNone(self.edit('"version": "0.1.0"', '"version": "0.2.0"'))

    def test_fails_open_when_disk_or_result_is_not_json(self):
        self.write_disk('{"version": "0.1.0"')
        self.assertIsNone(self.edit('"version": "0.1.0"', '"version": "0.2.0"'))
        self.write_disk(PACKAGE_JSON)
        self.assertIsNone(self.edit('"version": "0.1.0",', '"version": "0.2.0"'))

    def test_fails_open_when_edit_fields_are_malformed(self):
        self.assertIsNone(write_guard.evaluate(call("Edit", {"file_path": self.path, "old_string": None, "new_string": '"version": "0.2.0"'})))
        self.assertIsNone(write_guard.evaluate(call("MultiEdit", {"file_path": self.path, "edits": "nope"})))


class PackageJsonWriteTests(PackageJsonCase):
    def test_denies_write_changing_version(self):
        self.write_disk('{"name": "x", "version": "0.1.0"}')
        result = write_guard.evaluate(call("Write", {"file_path": self.path, "content": '{"name": "x", "version": "0.2.0"}'}))
        self.assertEqual(decision(result), "deny")

    def test_denies_write_removing_version(self):
        self.write_disk('{"name": "x", "version": "0.1.0"}')
        result = write_guard.evaluate(call("Write", {"file_path": self.path, "content": '{"name": "x"}'}))
        self.assertEqual(decision(result), "deny")

    def test_permits_write_keeping_version(self):
        self.write_disk('{"name": "x", "version": "0.1.0"}')
        self.assertIsNone(write_guard.evaluate(call("Write", {"file_path": self.path, "content": '{"name": "y", "version": "0.1.0"}'})))

    def test_permits_write_when_file_missing(self):
        self.assertIsNone(write_guard.evaluate(call("Write", {"file_path": self.path, "content": '{"name": "x", "version": "0.0.0"}'})))

    def test_fails_open_when_either_side_is_not_json(self):
        self.write_disk("not json")
        self.assertIsNone(write_guard.evaluate(call("Write", {"file_path": self.path, "content": '{"version": "9.9.9"}'})))
        self.write_disk('{"version": "0.1.0"}')
        self.assertIsNone(write_guard.evaluate(call("Write", {"file_path": self.path, "content": "not json"})))


class FailOpenTests(unittest.TestCase):
    def test_missing_path_is_ignored(self):
        self.assertIsNone(write_guard.evaluate(call("Edit", {"old_string": "a", "new_string": "b"})))

    def test_garbage_input_keeps_main_silent(self):
        for garbage in ("", "{", '{"tool_name": "Edit"}', "[1]"):
            with self.subTest(garbage=garbage):
                out = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(garbage)), redirect_stdout(out):
                    with self.assertRaises(SystemExit) as raised:
                        write_guard.main()
                self.assertEqual(raised.exception.code, 0)
                self.assertEqual(out.getvalue(), "")

    def test_main_prints_deny_json(self):
        payload = json.dumps(call("Write", {"file_path": f"{CWD}/.env", "content": ""}))
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(payload)), redirect_stdout(out):
            with self.assertRaises(SystemExit):
                write_guard.main()
        self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
