import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "announce-instructions.py")
SPEC = importlib.util.spec_from_file_location("announce_instructions", HOOK_PATH)
announce_instructions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(announce_instructions)

AGENTS_MD = "# Title\n\nintro\n\n## Rules\n\n- one\n\n### Detail\n\nbody\n\n#### Deep\n"
HEADINGS = "# Title\n## Rules\n### Detail"
GATE = "Writes into this repository are gated on reading it in full."
SOURCES = ("startup", "resume", "clear", "compact")


def payload(cwd, source="startup"):
    return {"hook_event_name": "SessionStart", "session_id": "s", "cwd": cwd, "source": source}


def pointer(cwd, source="startup"):
    return announce_instructions.evaluate(payload(cwd, source))


def run_script(stdin):
    return subprocess.run([sys.executable, HOOK_PATH], input=stdin, capture_output=True, text=True)


class RepositoryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.realpath(self.tmp.name)
        self.root = os.path.join(self.base, "repo")
        self.cwd = os.path.join(self.root, "packages", "x")
        self.instructions = os.path.join(self.root, "AGENTS.md")
        os.makedirs(os.path.join(self.root, ".git"))
        os.makedirs(self.cwd)

    def write(self, relative, text):
        path = os.path.join(self.root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def expected(self, headings=HEADINGS):
        lines = [self.instructions, *([headings] if headings else []), "", GATE]
        return "\n".join(lines)


class PointerTests(RepositoryCase):
    def test_prints_the_pointer_for_every_session_source(self):
        self.write("AGENTS.md", AGENTS_MD)
        for source in SOURCES:
            with self.subTest(source=source):
                self.assertEqual(pointer(self.cwd, source), self.expected())

    def test_headings_beyond_forty_are_replaced_by_an_ellipsis(self):
        self.write("AGENTS.md", "".join(f"## H{n}\n" for n in range(41)))
        headings = "\n".join(f"## H{n}" for n in range(40))
        self.assertEqual(pointer(self.cwd), f"{self.instructions}\n{headings}\n…\n\n{GATE}")


class ImportTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.write("AGENTS.md", AGENTS_MD)

    def test_silent_when_the_root_claude_md_imports_agents_md(self):
        for claude_md in ("@AGENTS.md\n", "# Rules\n\n@AGENTS.md\n", "  @AGENTS.md  \n", "\t@AGENTS.md\n", "@AGENTS.md"):
            with self.subTest(claude_md=claude_md):
                self.write("CLAUDE.md", claude_md)
                self.assertIsNone(pointer(self.cwd))


class RootTests(RepositoryCase):
    def test_silent_without_an_agents_md_at_the_root(self):
        self.assertIsNone(pointer(self.cwd))

    def test_a_git_root_outranks_a_nearer_ancestor_holding_agents_md(self):
        self.write("packages/AGENTS.md", AGENTS_MD)
        self.write("AGENTS.md", AGENTS_MD)
        self.assertEqual(pointer(self.cwd), self.expected())

    def test_a_git_file_marks_the_root_as_a_git_directory_does(self):
        os.rmdir(os.path.join(self.root, ".git"))
        self.write(".git", "gitdir: /elsewhere/.git/worktrees/x\n")
        self.write("AGENTS.md", AGENTS_MD)
        self.assertEqual(pointer(self.cwd), self.expected())


class FailOpenTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.write("AGENTS.md", AGENTS_MD)

    def test_silent_when_the_hook_input_is_not_an_object(self):
        for hook_input in ([1], "x", None, 1):
            with self.subTest(hook_input=hook_input):
                self.assertIsNone(announce_instructions.evaluate(hook_input))


class ScriptTests(RepositoryCase):
    def test_script_prints_the_pointer_on_stdout_and_exits_0_with_empty_stderr(self):
        self.write("AGENTS.md", AGENTS_MD)
        completed = run_script(json.dumps(payload(self.cwd)))
        self.assertEqual(completed.stdout, f"{self.instructions}\n{HEADINGS}\n\n{GATE}\n")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
