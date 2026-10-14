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
DIRECTORY = object()
SLOW_CHECK = "#!/bin/bash\n/bin/bash -c 'sleep 5; :' {token}\necho '  foreign: staged'\nexit 1\n"
STUB_TIMEOUT = 0.2
KILL_DEADLINE = 2.0


def payload(source="startup"):
    return {"hook_event_name": "SessionStart", "session_id": "s", "cwd": "/tmp", "source": source}


def entry(path):
    if os.path.islink(path):
        return os.readlink(path)
    if os.path.isdir(path):
        return DIRECTORY
    with open(path, "rb") as handle:
        return os.stat(path).st_mode & 0o777, handle.read()


def snapshot(base):
    state = {}
    for root, directories, files in os.walk(base):
        for name in directories + files:
            path = os.path.join(root, name)
            state[os.path.relpath(path, base)] = entry(path)
    return state


def discard(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def create(path, state):
    if state is DIRECTORY:
        os.mkdir(path)
    elif isinstance(state, str):
        os.symlink(state, path)
    else:
        mode, content = state
        with open(path, "wb") as handle:
            handle.write(content)
        os.chmod(path, mode)


def restore(base, state):
    present = snapshot(base)
    for relative in sorted(present, reverse=True):
        if relative not in state:
            discard(os.path.join(base, relative))
    for relative in sorted(state):
        if present.get(relative) != state[relative]:
            path = os.path.join(base, relative)
            discard(path)
            create(path, state[relative])


class DriftNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        cls.addClassCleanup(directory.cleanup)
        cls.base = os.path.realpath(directory.name)
        cls.repo = os.path.join(cls.base, "repo")
        cls.apply = os.path.join(cls.repo, "apply.sh")
        cls.home = os.path.join(cls.base, ".claude")
        cls.agents_skills = os.path.join(cls.base, "agents-skills")
        cls.codex = os.path.join(cls.base, "codex")
        cls.local_bin = os.path.join(cls.base, "local-bin")
        cls.env = {
            "CLAUDE_CONFIG_DIR": cls.home,
            "AGENTS_SKILLS_DIR": cls.agents_skills,
            "CODEX_HOME": cls.codex,
            "CLAUDE_LOCAL_BIN": cls.local_bin,
        }
        shutil.copytree(REPO, cls.repo, ignore=IGNORED)
        os.makedirs(cls.codex)
        applied = cls.run_apply()
        if applied.returncode != 0:
            raise AssertionError(applied.stdout + applied.stderr)
        cls.applied = snapshot(cls.base)

    def setUp(self):
        self.addCleanup(self.restore_applied_tree)

    def restore_applied_tree(self):
        restore(self.base, self.applied)

    @classmethod
    def run_apply(cls, *arguments):
        return subprocess.run(
            ["/bin/bash", cls.apply, *arguments],
            cwd=cls.repo,
            env={**os.environ, **cls.env},
            capture_output=True,
            text=True,
        )

    def notice(self, hook_input=ABSENT):
        with mock.patch.dict(os.environ, self.env):
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

    def write_check(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def assert_nothing_survives(self, token):
        deadline = time.monotonic() + KILL_DEADLINE
        while subprocess.run(["pgrep", "-f", token], capture_output=True).returncode == 0:
            if time.monotonic() > deadline:
                self.fail(f"a process of the check's group outlived the timeout: {token}")
            time.sleep(0.05)

    def test_silent_for_every_session_source(self):
        for source in SOURCES:
            with self.subTest(source=source):
                self.assertIsNone(self.notice(payload(source)))

    def test_a_foreign_file_under_the_skills_dir_is_named(self):
        foreign = self.foreign_file()
        self.assertEqual(self.notice(), self.expected(f"foreign: {foreign}"))

    def test_script_prints_nothing_and_exits_0_for_unusable_stdin_on_a_drifted_tree(self):
        self.foreign_file()
        for stdin in GARBAGE:
            with self.subTest(stdin=stdin):
                completed = self.run_script(stdin)
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
