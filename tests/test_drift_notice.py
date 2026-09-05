import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK_PATH = os.path.join(REPO, "claude", "hooks", "drift-notice.py")
SPEC = importlib.util.spec_from_file_location("drift_notice", HOOK_PATH)
drift_notice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drift_notice)

IGNORED = shutil.ignore_patterns(".git", "__pycache__", ".DS_Store")
SOURCES = ("startup", "resume", "clear", "compact")
GARBAGE = ("", "{", "[1]", '"x"', "null")
ABSENT = object()
SLOW_CHECK = "#!/bin/bash\n/bin/bash -c 'sleep 5; :' {token}\necho '  foreign: staged'\nexit 1\n"
STAGED_DRIFT = "#!/bin/bash\necho '  foreign: x'\nexit 1\n"
STUB_TIMEOUT = 0.2
KILL_DEADLINE = 2.0


def payload(source="startup"):
    return {"hook_event_name": "SessionStart", "session_id": "s", "cwd": "/tmp", "source": source}


class LiveTreeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(self.base, "repo")
        self.apply = os.path.join(self.repo, "apply.sh")
        self.home = os.path.join(self.base, ".claude")
        self.agents_skills = os.path.join(self.base, "agents-skills")
        self.codex = os.path.join(self.base, "codex")
        self.local_bin = os.path.join(self.base, "local-bin")
        shutil.copytree(REPO, self.repo, ignore=IGNORED)
        os.makedirs(self.codex)
        self.env = {
            "CLAUDE_CONFIG_DIR": self.home,
            "AGENTS_SKILLS_DIR": self.agents_skills,
            "CODEX_HOME": self.codex,
            "CLAUDE_LOCAL_BIN": self.local_bin,
        }
        applied = self.run_apply()
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

    def run_apply(self, *arguments):
        return subprocess.run(
            ["/bin/bash", self.apply, *arguments],
            cwd=self.repo,
            env={**os.environ, **self.env},
            capture_output=True,
            text=True,
        )

    def notice(self, hook_input=ABSENT, **overrides):
        with mock.patch.dict(os.environ, {**self.env, **overrides}):
            return drift_notice.evaluate(payload() if hook_input is ABSENT else hook_input)

    def run_script(self, stdin, **overrides):
        return subprocess.run(
            [sys.executable, HOOK_PATH],
            input=stdin,
            env={**os.environ, **self.env, **overrides},
            capture_output=True,
            text=True,
        )

    def expected(self, drift):
        return f"ai-config drift: {drift}; run {self.apply}"

    def foreign_file(self):
        path = os.path.join(self.home, "skills", "other.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("other\n")
        return path

    def owned_link(self, *relative):
        return os.path.join(self.home, *relative), os.path.join(self.repo, "claude", *relative)

    def write_check(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def assert_nothing_survives(self, token):
        deadline = time.monotonic() + KILL_DEADLINE
        while subprocess.run(["pgrep", "-f", token], capture_output=True).returncode == 0:
            if time.monotonic() > deadline:
                self.fail(f"a process of the check's group outlived the timeout: {token}")
            time.sleep(0.05)

    def edit_settings(self, mutate):
        path = os.path.join(self.home, "settings.json")
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        mutate(document)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(document, indent=2) + "\n")


class CleanTreeTests(LiveTreeCase):
    def test_silent_when_the_live_tree_matches_the_repository(self):
        self.assertIsNone(self.notice())

    def test_silent_for_every_session_source(self):
        for source in SOURCES:
            with self.subTest(source=source):
                self.assertIsNone(self.notice(payload(source)))


class DriftTests(LiveTreeCase):
    def test_a_foreign_file_under_the_skills_dir_is_named(self):
        foreign = self.foreign_file()
        self.assertEqual(self.notice(), self.expected(f"foreign: {foreign}"))

    def test_a_deleted_link_is_named_as_the_link_it_needs(self):
        target, link_source = self.owned_link("rules", "git.md")
        os.remove(target)
        self.assertEqual(self.notice(), self.expected(f"link: {target} -> {link_source}"))

    def test_an_edited_agents_md_is_named_as_a_regeneration(self):
        agents_md = os.path.join(self.codex, "AGENTS.md")
        with open(agents_md, "a", encoding="utf-8") as handle:
            handle.write("\nedited by hand\n")
        self.assertEqual(self.notice(), self.expected(f"generate: {agents_md}"))

    def test_a_removed_manifest_default_is_named_as_a_settings_change(self):
        self.edit_settings(lambda document: document.pop("attribution"))
        self.assertEqual(self.notice(), self.expected("settings: would change"))

    def test_the_drift_line_is_printed_for_every_session_source(self):
        target, link_source = self.owned_link("rules", "git.md")
        os.remove(target)
        for source in SOURCES:
            with self.subTest(source=source):
                self.assertEqual(self.notice(payload(source)), self.expected(f"link: {target} -> {link_source}"))

    def test_a_foreign_symlink_at_an_owned_path_is_named_as_a_conflict(self):
        target, _ = self.owned_link("rules", "git.md")
        os.remove(target)
        os.symlink("/etc/hosts", target)
        self.assertEqual(self.notice(), self.expected(f"CONFLICT: {target} (foreign symlink -> /etc/hosts)"))

    def test_an_absent_codex_home_is_passed_over_for_the_settings_change(self):
        self.edit_settings(lambda document: document.pop("attribution"))
        self.assertEqual(
            self.notice(CODEX_HOME=os.path.join(self.base, "no-codex")),
            self.expected("settings: would change"),
        )

    def test_an_empty_claude_config_dir_falls_back_to_the_home_directory(self):
        foreign = self.foreign_file()
        self.assertEqual(
            self.notice(CLAUDE_CONFIG_DIR="", HOME=self.base),
            self.expected(f"foreign: {foreign}"),
        )


class FailOpenTests(LiveTreeCase):
    def setUp(self):
        super().setUp()
        self.foreign_file()

    def test_silent_without_a_claude_md_link_in_the_config_dir(self):
        os.remove(os.path.join(self.home, "CLAUDE.md"))
        self.write_check(os.path.join(self.base, "apply.sh"), STAGED_DRIFT)
        self.assertIsNone(self.notice())

    def test_silent_when_apply_cannot_source_its_link_library(self):
        os.remove(os.path.join(self.repo, "lib", "links.sh"))
        self.assertIsNone(self.notice())

    def test_silent_without_an_apply_script_in_the_repository(self):
        os.remove(self.apply)
        self.assertIsNone(self.notice())

    def test_silent_when_the_hook_input_is_not_an_object(self):
        for hook_input in ([1], "x", None, 1):
            with self.subTest(hook_input=hook_input):
                self.assertIsNone(self.notice(hook_input))


class ScriptTests(LiveTreeCase):
    def test_script_prints_the_drift_line_on_stdout_and_exits_0_with_empty_stderr(self):
        foreign = self.foreign_file()
        completed = self.run_script(json.dumps(payload()))
        self.assertEqual(completed.stdout, self.expected(f"foreign: {foreign}") + "\n")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0)

    def test_script_prints_nothing_and_exits_0_on_a_clean_tree(self):
        completed = self.run_script(json.dumps(payload()))
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0)

    def test_script_prints_nothing_and_exits_0_for_unusable_stdin_on_a_drifted_tree(self):
        self.foreign_file()
        for stdin in GARBAGE:
            with self.subTest(stdin=stdin):
                completed = self.run_script(stdin)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr, "")
                self.assertEqual(completed.returncode, 0)

    def test_script_prints_nothing_and_exits_0_without_an_apply_script_on_a_drifted_tree(self):
        self.foreign_file()
        os.remove(self.apply)
        completed = self.run_script(json.dumps(payload()))
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0)

    def test_main_prints_nothing_exits_0_and_leaves_no_child_when_the_check_outlasts_its_timeout(self):
        token = uuid.uuid4().hex
        self.write_check(self.apply, SLOW_CHECK.format(token=token))
        out = io.StringIO()
        started = time.monotonic()
        with mock.patch.dict(os.environ, self.env), mock.patch.object(drift_notice, "CHECK_TIMEOUT", STUB_TIMEOUT):
            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload()))), redirect_stdout(out):
                with self.assertRaises(SystemExit) as raised:
                    drift_notice.main()
        elapsed = time.monotonic() - started
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertLess(elapsed, KILL_DEADLINE)
        self.assert_nothing_survives(token)


if __name__ == "__main__":
    unittest.main()
