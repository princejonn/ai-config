import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "write-guard.py")
SPEC = importlib.util.spec_from_file_location("write_guard", HOOK_PATH)
write_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(write_guard)

CWD = "/Users/someone/Projects/lindorm/lindorm-monorepo"
PACKAGE_JSON = '{\n  "name": "x",\n  "version": "0.1.0",\n  "private": true,\n  "engines": {\n    "node": ">=24",\n    "version": "1"\n  },\n  "dependencies": {\n    "a": "0.1.0"\n  }\n}\n'
GITIGNORE = "node_modules/\ndist/\ncoverage/\nbuild/\n"
TRACKED = ("packages/build/src/index.ts", "docs/build/index.md")
GENERATED_DIRECTORIES = ("node_modules/dep", "coverage", "packages/x/build")


def call(tool_name, tool_input, cwd=CWD):
    return {"hook_event_name": "PreToolUse", "tool_name": tool_name, "cwd": cwd, "tool_input": tool_input}


def decision(result):
    return None if result is None else result["hookSpecificOutput"]["permissionDecision"]


def reason(result):
    return result["hookSpecificOutput"]["permissionDecisionReason"]


def rule(result):
    return reason(result).split(" Permitted: ", 1)[0]


def edit(path, cwd=CWD):
    return write_guard.evaluate(call("Edit", {"file_path": path, "old_string": "a", "new_string": "b"}, cwd))


def write_tool(path, cwd=CWD):
    return write_guard.evaluate(call("Write", {"file_path": path, "content": ""}, cwd))


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


class RepositoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        root = os.path.realpath(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {"HOME": root, "XDG_CONFIG_HOME": os.path.join(root, ".config"), "GIT_CONFIG_SYSTEM": os.devnull})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = os.path.join(root, "repo")
        self.outside = os.path.join(root, "outside")
        os.makedirs(self.repo)
        os.makedirs(self.outside)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.com")
        self.git("config", "user.name", "fixture")
        self.write(".gitignore", GITIGNORE)
        for relative in TRACKED:
            self.write(relative, "")
        self.git("add", "-f", "--", ".gitignore", *TRACKED)
        self.git("commit", "-q", "-m", "chore: fixture", "--", ".gitignore", *TRACKED)
        for relative in GENERATED_DIRECTORIES:
            os.makedirs(os.path.join(self.repo, relative))

    def git(self, *args):
        subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True)

    def write(self, relative, text):
        path = os.path.join(self.repo, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def edit(self, relative):
        return edit(os.path.join(self.repo, relative), self.repo)

    def write_tool(self, relative):
        return write_tool(os.path.join(self.repo, relative), self.repo)


class EnvFileTests(unittest.TestCase):
    def test_denies_env_and_env_variants(self):
        for name in (".env", ".env.local", ".env.production"):
            with self.subTest(name=name):
                result = write_guard.evaluate(call("Write", {"file_path": f"{CWD}/{name}", "content": "A=1"}))
                self.assertEqual(decision(result), "deny")

    def test_denies_edit_of_env_file(self):
        self.assertEqual(decision(edit(f"{CWD}/.env")), "deny")

    def test_permits_env_example(self):
        self.assertIsNone(edit(f"{CWD}/.env.example"))

    def test_relative_path_resolves_against_cwd(self):
        self.assertEqual(decision(write_guard.evaluate(call("Write", {"file_path": ".env", "content": ""}))), "deny")


class GeneratedDirectoryTests(RepositoryCase):
    def test_permits_tracked_files_under_a_directory_named_like_build_output(self):
        for relative in TRACKED:
            with self.subTest(path=relative):
                self.assertIsNone(self.edit(relative))

    def test_denies_writes_into_git_ignored_directories(self):
        for relative, name in (("dist/index.js", "dist"), ("node_modules/dep/index.js", "node_modules"), ("coverage/lcov.info", "coverage"), ("packages/x/build/out.js", "build")):
            with self.subTest(path=relative):
                result = self.edit(relative)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), f"write-guard.py: '{name}' is a git-ignored generated directory and is read-only.")

    def test_denies_write_tool_into_a_git_ignored_directory(self):
        result = self.write_tool("dist/index.js")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only.")

    def test_denies_a_git_ignored_directory_absent_from_disk(self):
        self.assertFalse(os.path.exists(os.path.join(self.repo, "dist")))
        result = self.edit("dist/new/file.js")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only.")

    def test_permits_a_named_directory_that_git_does_not_ignore(self):
        self.write(".gitignore", "dist/\n")
        self.assertIsNone(self.edit("build/out.js"))

    def test_every_named_ancestor_is_checked_outermost_first(self):
        self.write(".gitignore", "dist/\n")
        self.assertEqual(rule(self.edit("build/dist/out.js")), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only.")
        self.write(".gitignore", GITIGNORE)
        self.assertEqual(rule(self.edit("dist/build/out.js")), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only.")

    def test_denies_a_named_directory_outside_any_repository(self):
        result = edit(os.path.join(self.outside, "dist", "index.js"), self.outside)
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'dist' is a generated directory by name and lies outside any repository.")

    def test_denies_a_named_directory_when_git_cannot_be_consulted(self):
        failures = {
            "absent": FileNotFoundError(),
            "timeout": subprocess.TimeoutExpired(cmd="git", timeout=5),
            "error": subprocess.CompletedProcess(args=["git"], returncode=128),
        }
        for label, failure in failures.items():
            with self.subTest(failure=label):
                with mock.patch("subprocess.run", side_effect=[failure]):
                    result = self.edit("dist/index.js")
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), "write-guard.py: 'dist' is a generated directory by name and git could not be consulted.")

    def test_deny_reason_names_the_source_as_the_permitted_form(self):
        self.assertEqual(reason(self.edit("dist/index.js")), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only. Permitted: edit the source that generates it.")

    def test_name_match_is_exact_not_substring(self):
        self.write(".gitignore", GITIGNORE + "builder/\ndistribution/\n")
        self.assertIsNone(self.edit("packages/x/builder/index.ts"))
        self.assertIsNone(self.edit("distribution/a.ts"))

    def test_a_file_named_like_a_generated_directory_is_source(self):
        self.assertIsNone(self.edit("build"))
        self.assertIsNone(self.edit("packages/x/dist"))

    def test_dotenv_and_git_store_rules_decide_before_git_is_consulted(self):
        self.assertEqual(rule(self.edit("dist/.env")), "write-guard.py: dotenv files hold secrets and are read-only.")
        with mock.patch("subprocess.run") as run:
            for relative in (".git/dist/x", "node_modules/dep/.git/config"):
                with self.subTest(path=relative):
                    self.assertEqual(rule(self.edit(relative)), "write-guard.py: the .git directory is git's own store and is read-only.")
        run.assert_not_called()

    def test_permits_source_files(self):
        self.assertIsNone(self.edit("packages/aegis/src/a.ts"))

    def test_dot_dot_traversal_into_a_git_ignored_directory_is_denied(self):
        result = self.edit("packages/x/src/../dist/index.js")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only.")

    def test_notebook_path_is_honoured(self):
        result = write_guard.evaluate(call("NotebookEdit", {"notebook_path": f"{self.repo}/dist/nb.ipynb", "new_source": ""}, self.repo))
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'dist' is a git-ignored generated directory and is read-only.")
        self.assertIsNone(write_guard.evaluate(call("NotebookEdit", {"notebook_path": f"{self.repo}/docs/nb.ipynb", "new_source": ""}, self.repo)))


class GitStoreTests(RepositoryCase):
    def test_permits_info_exclude(self):
        self.assertIsNone(self.edit(".git/info/exclude"))

    def test_permits_hooks(self):
        self.assertIsNone(self.edit(".git/hooks/pre-commit"))

    def test_denies_config(self):
        result = self.edit(".git/config")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(reason(result), "write-guard.py: the .git directory is git's own store and is read-only. Permitted: .git/info/exclude and .git/hooks/* only.")

    def test_denies_objects(self):
        result = self.edit(".git/objects/ab/cd")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: the .git directory is git's own store and is read-only.")

    def test_denies_the_hooks_directory_itself_and_paths_below_info_exclude(self):
        for relative in (".git/hooks", ".git/info/exclude/x"):
            with self.subTest(path=relative):
                self.assertEqual(rule(self.edit(relative)), "write-guard.py: the .git directory is git's own store and is read-only.")


class SymlinkTests(RepositoryCase):
    def test_symlink_into_a_git_ignored_directory_is_denied(self):
        link = os.path.join(self.repo, "alias")
        os.symlink(os.path.join(self.repo, "node_modules"), link)
        result = edit(f"{link}/dep/index.js", self.repo)
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'node_modules' is a git-ignored generated directory and is read-only.")

    def test_symlink_to_a_source_directory_is_permitted(self):
        source = os.path.join(self.repo, "src")
        os.makedirs(source)
        link = os.path.join(self.repo, "dist")
        os.symlink(source, link)
        self.assertIsNone(edit(f"{link}/a.ts", self.repo))


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

    def test_permits_dependency_range_matching_the_version_value(self):
        self.assertIsNone(self.edit('"a": "0.1.0"', '"a": "0.2.0"'))

    def test_permits_edit_spanning_an_unchanged_version_line(self):
        old = '  "name": "x",\n  "version": "0.1.0",\n  "private": true'
        new = '  "name": "y",\n  "version": "0.1.0",\n  "private": false'
        self.assertIsNone(self.edit(old, new))

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
