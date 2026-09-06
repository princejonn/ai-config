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
BOM = "\ufeff"
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

    def test_prints_the_pointer_from_the_root_itself(self):
        self.write("AGENTS.md", AGENTS_MD)
        self.assertEqual(pointer(self.root), self.expected())

    def test_path_is_the_realpath_of_the_root(self):
        self.write("AGENTS.md", AGENTS_MD)
        link = os.path.join(self.base, "link")
        os.symlink(self.cwd, link)
        self.assertEqual(pointer(link), self.expected())

    def test_prints_the_path_and_the_gate_sentence_for_an_agents_md_without_headings(self):
        self.write("AGENTS.md", "prose only\n\n#### Deep\n")
        self.assertEqual(pointer(self.cwd), f"{self.instructions}\n\n{GATE}")

    def test_a_byte_order_mark_does_not_hide_the_first_heading(self):
        self.write("AGENTS.md", BOM + AGENTS_MD)
        self.assertEqual(pointer(self.cwd), self.expected())

    def test_headings_are_verbatim_and_in_file_order(self):
        self.write("AGENTS.md", "### Third\n# First\n## Second\n")
        self.assertEqual(pointer(self.cwd), f"{self.instructions}\n### Third\n# First\n## Second\n\n{GATE}")

    def test_a_hash_run_without_a_following_space_and_word_is_not_a_heading(self):
        self.write("AGENTS.md", "#Title\n#\n# \n####  Deep\n ## Indented\n##  Wide\n## Kept\n")
        self.assertEqual(pointer(self.cwd), f"{self.instructions}\n## Kept\n\n{GATE}")

    def test_forty_headings_are_printed_whole(self):
        self.write("AGENTS.md", "".join(f"## H{n}\n" for n in range(40)))
        headings = "\n".join(f"## H{n}" for n in range(40))
        self.assertEqual(pointer(self.cwd), f"{self.instructions}\n{headings}\n\n{GATE}")

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

    def test_silent_when_the_root_claude_md_imports_the_same_file_as_dot_slash(self):
        for claude_md in ("@./AGENTS.md\n", "# Rules\n\n@./AGENTS.md\n", "  @./AGENTS.md  \n", "@./AGENTS.md"):
            with self.subTest(claude_md=claude_md):
                self.write("CLAUDE.md", claude_md)
                self.assertIsNone(pointer(self.cwd))

    def test_a_byte_order_mark_does_not_hide_the_import(self):
        self.write("CLAUDE.md", BOM + "@AGENTS.md\n")
        self.assertIsNone(pointer(self.cwd))

    def test_prints_when_the_root_claude_md_does_not_import_agents_md(self):
        for claude_md in ("# Rules\n\nnothing\n", "@rules/git.md\n", "see @AGENTS.md for the rules\n", "@AGENTS.md.bak\n", "@../AGENTS.md\n", ""):
            with self.subTest(claude_md=claude_md):
                self.write("CLAUDE.md", claude_md)
                self.assertEqual(pointer(self.cwd), self.expected())

    def test_an_import_in_a_subdirectory_claude_md_does_not_count(self):
        self.write("packages/x/CLAUDE.md", "@AGENTS.md\n")
        self.assertEqual(pointer(self.cwd), self.expected())

    def test_an_unreadable_claude_md_counts_as_not_importing(self):
        path = self.write("CLAUDE.md", "@AGENTS.md\n")
        os.chmod(path, 0o000)
        self.addCleanup(os.chmod, path, 0o600)
        if os.access(path, os.R_OK):
            self.skipTest("permission bits do not bind this user")
        self.assertEqual(pointer(self.cwd), self.expected())

    def test_a_claude_md_that_is_not_utf_8_counts_as_not_importing(self):
        with open(os.path.join(self.root, "CLAUDE.md"), "wb") as handle:
            handle.write(b"@AGENTS.md\n\xff\xfe\n")
        self.assertEqual(pointer(self.cwd), self.expected())


class RootTests(RepositoryCase):
    def test_silent_without_an_agents_md_at_the_root(self):
        self.assertIsNone(pointer(self.cwd))

    def test_silent_when_agents_md_lives_only_in_a_subdirectory(self):
        self.write("packages/x/AGENTS.md", AGENTS_MD)
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

    def test_the_nearest_ancestor_holding_agents_md_is_the_root_without_a_git_ancestor(self):
        os.rmdir(os.path.join(self.root, ".git"))
        self.write("AGENTS.md", AGENTS_MD)
        self.assertEqual(pointer(self.cwd), self.expected())

    def test_the_nearest_of_two_ancestors_holding_agents_md_is_the_root(self):
        os.rmdir(os.path.join(self.root, ".git"))
        self.write("AGENTS.md", AGENTS_MD)
        nearer = self.write("packages/AGENTS.md", AGENTS_MD)
        self.assertEqual(pointer(self.cwd), f"{nearer}\n{HEADINGS}\n\n{GATE}")

    def test_silent_when_no_ancestor_holds_a_git_entry_or_agents_md(self):
        os.rmdir(os.path.join(self.root, ".git"))
        self.assertIsNone(pointer(self.cwd))

    def test_a_directory_named_agents_md_is_not_instructions(self):
        os.makedirs(os.path.join(self.root, "AGENTS.md"))
        self.assertIsNone(pointer(self.cwd))


class FailOpenTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.write("AGENTS.md", AGENTS_MD)

    def test_silent_when_cwd_does_not_exist(self):
        self.assertIsNone(pointer(os.path.join(self.cwd, "gone")))

    def test_silent_when_cwd_is_missing_or_not_a_string(self):
        for hook_input in ({"hook_event_name": "SessionStart", "source": "startup"}, {"cwd": None}, {"cwd": ""}, {"cwd": 1}):
            with self.subTest(hook_input=hook_input):
                self.assertIsNone(announce_instructions.evaluate(hook_input))

    def test_silent_when_the_hook_input_is_not_an_object(self):
        for hook_input in ([1], "x", None, 1):
            with self.subTest(hook_input=hook_input):
                self.assertIsNone(announce_instructions.evaluate(hook_input))

    def test_silent_when_agents_md_is_not_utf_8(self):
        with open(self.instructions, "wb") as handle:
            handle.write(b"# Title\n\xff\xfe\n")
        self.assertIsNone(pointer(self.cwd))

    def test_silent_when_agents_md_is_unreadable(self):
        os.chmod(self.instructions, 0o000)
        self.addCleanup(os.chmod, self.instructions, 0o600)
        if os.access(self.instructions, os.R_OK):
            self.skipTest("permission bits do not bind this user")
        self.assertIsNone(pointer(self.cwd))


class ScriptTests(RepositoryCase):
    def test_script_prints_the_pointer_on_stdout_and_exits_0_with_empty_stderr(self):
        self.write("AGENTS.md", AGENTS_MD)
        completed = run_script(json.dumps(payload(self.cwd)))
        self.assertEqual(completed.stdout, f"{self.instructions}\n{HEADINGS}\n\n{GATE}\n")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0)

    def test_script_prints_nothing_and_exits_0_when_the_import_is_present(self):
        self.write("AGENTS.md", AGENTS_MD)
        self.write("CLAUDE.md", "@AGENTS.md\n")
        completed = run_script(json.dumps(payload(self.cwd)))
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(completed.returncode, 0)

    def test_script_prints_nothing_and_exits_0_for_unusable_stdin(self):
        self.write("AGENTS.md", AGENTS_MD)
        for stdin in ("", "{", "[1]", '"x"', "null", "{}", json.dumps({"cwd": os.path.join(self.cwd, "gone")})):
            with self.subTest(stdin=stdin):
                completed = run_script(stdin)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr, "")
                self.assertEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
