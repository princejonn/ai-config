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

CWD = "/Users/someone/Projects/example/example-monorepo"
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


class PackageJsonCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "package.json")

    def write_disk(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def edit(self, old, new):
        tool_input = {"file_path": self.path, "old_string": old, "new_string": new}
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


class EnvFileTests(unittest.TestCase):
    def test_denies_env_and_env_variants(self):
        for name in (".env", ".env.local", ".env.production"):
            with self.subTest(name=name):
                result = write_guard.evaluate(call("Write", {"file_path": f"{CWD}/{name}", "content": "A=1"}))
                self.assertEqual(decision(result), "deny")

    def test_permits_env_example(self):
        self.assertIsNone(edit(f"{CWD}/.env.example"))


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


class GitStoreTests(RepositoryCase):
    def test_permits_info_exclude(self):
        self.assertIsNone(self.edit(".git/info/exclude"))

    def test_denies_config(self):
        result = self.edit(".git/config")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(reason(result), "write-guard.py: the .git directory is git's own store and is read-only. Permitted: .git/info/exclude and .git/hooks/* only.")


class SymlinkTests(RepositoryCase):
    def test_symlink_into_a_git_ignored_directory_is_denied(self):
        link = os.path.join(self.repo, "alias")
        os.symlink(os.path.join(self.repo, "node_modules"), link)
        result = edit(f"{link}/dep/index.js", self.repo)
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "write-guard.py: 'node_modules' is a git-ignored generated directory and is read-only.")


class PackageJsonEditTests(PackageJsonCase):
    def setUp(self):
        super().setUp()
        self.write_disk(PACKAGE_JSON)

    def test_denies_edit_touching_version_line(self):
        self.assertEqual(self.edit('"version": "0.1.0"', '"version": "0.2.0"'), "deny")

    def test_permits_edit_of_other_fields(self):
        self.assertIsNone(self.edit('"private": true', '"private": false'))


class PackageJsonWriteTests(PackageJsonCase):
    def test_denies_write_changing_version(self):
        self.write_disk('{"name": "x", "version": "0.1.0"}')
        result = write_guard.evaluate(call("Write", {"file_path": self.path, "content": '{"name": "x", "version": "0.2.0"}'}))
        self.assertEqual(decision(result), "deny")


class FailOpenTests(unittest.TestCase):
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
