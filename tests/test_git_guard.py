import importlib.util
import io
import itertools
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "git-guard.py")
SPEC = importlib.util.spec_from_file_location("git_guard", HOOK_PATH)
git_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(git_guard)

MONOREPO = "/Users/someone/Projects/example/example-monorepo"
TMPDIR = "/private/tmp/claude-501/abc"
IGNORED = "node_modules/\ndist/\ncoverage/\n*.pyc\n__pycache__/\nlink\n/build/\n*.log\n!keep.log\n**/cache/\n/**/staging/\n**/**/twice/\n"
RM_RULE = "rm outside $TMPDIR, the scratchpad or a git-ignored path deletes work the tree cannot regenerate."
SUBSTITUTION_RULE = "delete target carries a shell substitution the guard cannot resolve."
BUDGET_RULE = "the guard's 8 s budget ran out before every delete target was judged."
SUBJECT_RULE = "commit subjects follow Conventional Commits: <type>(<scope>): <description>."
SUBJECT_PERMITTED = "types build chore ci docs feat fix perf refactor revert style test."
SECTION_RULE = "a bare § is an internal reference; commit messages stand alone."
SECTION_PERMITTED = "qualify it: RFC 6749 §3.1.1, OIDC Core §3.1.2.1."
PAGER_RULE = "piping a test or verify run through tail or head hides the runner's summary."
PAGER_PERMITTED = 'redirect: <command> > "$TMPDIR/out.txt" 2>&1, then read the file.'
STASH_RULE = "git stash silently destroys uncommitted work in a shared tree."
CLEAN_RULE = "git clean deletes untracked work in a shared tree."
STDIN_RULE = "git commit -F - takes the message from a pipe or stdin the guard cannot read."
PUSH_RULE = "a push in any other form can reach the default branch without the prompt its name carries."
PUSH_NESTED_RULE = "a push inside a subshell, a command substitution or a find action reaches the default branch with no prompt at all."
PUSH_PERMITTED = "git push origin <branch>."
PUSH_NESTED_PERMITTED = "git push origin <branch> as its own command."
PAUSED_RULE = "a chore(paused): commit lands only on a paused/<N>-<k> branch, read before the command runs."
PAUSED_PERMITTED = "git switch -c paused/<N>-<k> as its own command, then git commit -F - -- <paths>."
GH_REPO_RULE = "a gh --repo flag quoted with its value is one shell word that never reaches gh as a flag."
GH_REPO_PERMITTED = "--repo <owner/name> as two shell words."
GH_MERGE_RULE = "merging a pull request, enabling its auto-merge or updating its branch is the owner's decision."
GH_MERGE_PERMITTED = "leave the pull request open; gh pr view <N> --repo <owner/name> reads its state."
GH_ALIAS_RULE = "gh alias set/import defines a command the guard cannot see."
GH_ALIAS_PERMITTED = "the plain gh command."
GH_API_BODY_RULE = "a gh api body read from a file or stdin is text the guard cannot read."
GH_API_BODY_PERMITTED = "the fields as words in the command: -f key=value."
GH_CLOSING_RULE = "a closing keyword before an issue reference in pull-request text closes the issue when the pull request merges."
GH_CLOSING_PERMITTED = "Refs #<N>, which links the issue and closes nothing."
GH_TEXT_PERMITTED = "a literal -t/-b value as its own word or --title=/--body=<value>, -F - with a heredoc, or -F <scratchpad file> as the whole command."
FAKE_GIT = f"""#!{sys.executable}
import os, sys, time
time.sleep(float(os.environ["FAKE_GIT_SLEEP"]))
paths = sys.stdin.buffer.read().split(b"\\0")[:-1]
sys.stdout.buffer.write(b"".join(b"fake\\x001\\x00*\\x00" + path + b"\\x00" for path in paths))
sys.exit(0 if paths else 1)
"""


def bash(command, cwd=MONOREPO):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}}


def decision(result):
    if result is None:
        return None
    verdict = result["hookSpecificOutput"]["permissionDecision"]
    if verdict != "deny":
        raise AssertionError(f"a hook decision is deny or silence, got {verdict!r}")
    return verdict


def reason(result):
    if decision(result) != "deny":
        raise AssertionError(f"expected a deny, got {result!r}")
    return result["hookSpecificOutput"]["permissionDecisionReason"].removeprefix(f"{git_guard.HOOK}: ")


def rule(result):
    return reason(result).partition(" Permitted: ")[0]


def permitted(result):
    return reason(result).partition(" Permitted: ")[2]


def evaluate(command, cwd=MONOREPO):
    return git_guard.evaluate(bash(command, cwd))


class GitStashTests(unittest.TestCase):
    def test_denies_bare_stash(self):
        self.assertEqual(decision(evaluate("git stash")), "deny")

    def test_denies_stash_pop_and_push(self):
        self.assertEqual(decision(evaluate("git stash pop")), "deny")
        self.assertEqual(decision(evaluate("git stash push -m wip")), "deny")
        self.assertEqual(decision(evaluate("git stash -u")), "deny")
        self.assertEqual(decision(evaluate("git stash -m list")), "deny")
        self.assertEqual(rule(evaluate("git stash -m list")), "git stash silently destroys uncommitted work in a shared tree.")

    def test_permits_stash_list_and_show(self):
        self.assertIsNone(evaluate("git stash list"))
        self.assertIsNone(evaluate("git stash show"))
        self.assertIsNone(evaluate("git stash show -p"))
        self.assertIsNone(evaluate("git stash show -p stash@{0}"))


class GitResetCleanTests(unittest.TestCase):
    def test_denies_reset_hard_and_merge(self):
        self.assertEqual(decision(evaluate("git reset --hard HEAD~1")), "deny")
        self.assertEqual(decision(evaluate("git reset --merge")), "deny")

    def test_permits_mixed_reset(self):
        self.assertIsNone(evaluate("git reset HEAD -- packages/core/src/x.ts"))

    def test_denies_clean(self):
        self.assertEqual(decision(evaluate("git clean -fdx")), "deny")


class GitCheckoutRestoreSwitchTests(unittest.TestCase):
    def test_denies_tree_wide_checkout(self):
        self.assertEqual(decision(evaluate("git checkout .")), "deny")
        self.assertEqual(decision(evaluate("git checkout main")), "deny")

    def test_permits_pathspec_scoped_checkout(self):
        self.assertIsNone(evaluate("git checkout -- packages/core/src/a.ts"))
        self.assertIsNone(evaluate("git checkout HEAD -- packages/core/src/a.ts"))
        self.assertIsNone(evaluate("git checkout -- path/to/file"))

    def test_denies_tree_wide_pathspec_after_double_dash(self):
        for spec in (".", "./", ":/", "*", "':(top)'", ":/src", "./.", ":", "'**'", "..", "../..", "$PWD", "${PWD}", "$PWD/"):
            for subcommand in ("checkout", "restore"):
                with self.subTest(subcommand=subcommand, spec=spec):
                    result = evaluate(f"git {subcommand} -- {spec}")
                    self.assertEqual(decision(result), "deny")
                    self.assertEqual(rule(result), f"tree-wide git {subcommand} pathspec reverts everyone's uncommitted work.")
        self.assertEqual(decision(evaluate("git checkout HEAD -- packages/core .")), "deny")
        self.assertEqual(decision(evaluate("git restore --staged -- .")), "deny")

    def test_denies_absolute_pathspec_equal_to_repo_root(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as root:
            os.makedirs(os.path.join(root, ".git"))
            cwd = os.path.join(root, "packages", "core")
            os.makedirs(cwd)
            self.assertEqual(decision(evaluate(f"git checkout -- {root}", cwd=cwd)), "deny")
            self.assertEqual(decision(evaluate(f"git restore --staged -- {root}/", cwd=cwd)), "deny")
            self.assertEqual(decision(evaluate(f"git checkout -- {cwd}", cwd=cwd)), "deny")
            self.assertIsNone(evaluate(f"git checkout -- {cwd}/src", cwd=cwd))
            self.assertIsNone(evaluate(f"git restore -- {root}/packages/other", cwd=cwd))

    def test_denies_checkout_pathspec_with_a_substitution(self):
        for subcommand in ("checkout", "restore"):
            for spec in ("$(pwd)", '"${DIR}"', "$DIR", "$PWDX", "${PWDX}", "`pwd`", "src/$(basename x)"):
                with self.subTest(subcommand=subcommand, spec=spec):
                    result = evaluate(f"git {subcommand} -- {spec}")
                    self.assertEqual(decision(result), "deny")
                    self.assertEqual(rule(result), f"git {subcommand} pathspec carries a shell substitution the guard cannot resolve.")
        result = evaluate('git checkout -- "$PWD"')
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "tree-wide git checkout pathspec reverts everyone's uncommitted work.")

    def test_denies_tree_wide_restore(self):
        self.assertEqual(decision(evaluate("git restore .")), "deny")
        self.assertEqual(decision(evaluate("git restore --staged .")), "deny")

    def test_denies_switch_discard_or_force(self):
        self.assertEqual(decision(evaluate("git switch --discard-changes main")), "deny")
        self.assertEqual(decision(evaluate("git switch -f main")), "deny")

    def test_permits_plain_switch_and_create(self):
        self.assertIsNone(evaluate("git switch main"))
        self.assertIsNone(evaluate("git switch -c feat/x"))
        self.assertIsNone(evaluate("git switch -cfeat/x"))


class GitPushTests(unittest.TestCase):
    def assert_denied(self, commands, expected=PUSH_RULE, alternative=PUSH_PERMITTED):
        for command in commands:
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), expected)
                self.assertEqual(permitted(result), alternative)

    def test_permits_a_push_that_names_its_branch(self):
        for command in ("git push origin feature/x", "git push origin main", "git push origin release-1.2"):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_denies_a_push_that_names_no_branch(self):
        self.assert_denied(("git push", "git push origin"))

    def test_denies_pushing_the_current_head(self):
        self.assert_denied(("git push origin HEAD", "git push origin @"))

    def test_denies_a_source_destination_refspec(self):
        self.assert_denied(("git push origin HEAD:main", "git push origin feature/x:main", "git push origin :feature/x"))

    def test_denies_a_force_push(self):
        self.assert_denied(
            (
                "git push --force origin main",
                "git push -f origin feature/x",
                "git push --force-with-lease origin HEAD",
                "git push origin +main",
                "git push --force origin feature/x",
                "git push origin +feature/x",
            )
        )

    def test_denies_setting_the_upstream(self):
        self.assert_denied(("git push -u origin main", "git push --set-upstream origin feature/x"))

    def test_denies_pushing_every_ref(self):
        self.assert_denied(("git push --all origin", "git push --mirror origin", "git push --tags origin"))

    def test_denies_deleting_a_remote_branch(self):
        self.assert_denied(("git push origin --delete feature/x", "git push --delete origin feature/x"))

    def test_denies_a_flag_anywhere_in_the_push(self):
        self.assert_denied(
            (
                "git push --quiet origin feature/x",
                "git push origin feature/x --quiet",
                "git push origin feature/x --no-verify",
                "git -C packages/core push origin feature/x",
            )
        )

    def test_denies_a_remote_other_than_origin(self):
        self.assert_denied(("git push upstream feature/x", "git push git@github.com:owner/name.git main"))

    def test_denies_more_than_one_refspec(self):
        self.assert_denied(("git push origin feature/x feature/y", "git push origin main feature/x"))

    def test_denies_a_qualified_ref_in_place_of_a_branch(self):
        self.assert_denied(("git push origin refs/heads/main", "git push origin heads/main", "git push origin tags/v1"))

    def test_denies_a_push_whose_text_is_not_the_permitted_form(self):
        self.assert_denied(
            (
                'git push origin "main"',
                "git push origin $(git branch --show-current)",
                "git push  origin  main",
                "git push origin main # ship it",
                "sudo git push origin main",
            )
        )

    def test_denies_a_push_a_subshell_or_a_substitution_runs(self):
        self.assert_denied(
            (
                "(git push origin main)",
                "$(git push origin feature/x)",
                "echo `git push origin main`",
                'bash -c "git push origin main"',
                'eval "git push origin main"',
            ),
            expected=PUSH_NESTED_RULE,
            alternative=PUSH_NESTED_PERMITTED,
        )

    def test_denies_a_push_a_find_action_runs(self):
        self.assert_denied(
            ("find . -name '*.ts' -exec git push origin main \\;", "find . -type f -execdir git push origin feature/x \\;"),
            expected=PUSH_NESTED_RULE,
            alternative=PUSH_NESTED_PERMITTED,
        )

    def test_permits_deleting_a_paused_branch(self):
        for command in (
            "git push origin --delete paused/12-1",
            "git push origin --delete paused/1-1",
            "git push origin --delete paused/123-45",
            "git push origin --delete paused/12-1 2>&1",
            "git branch -D paused/12-1 && git push origin --delete paused/12-1",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_denies_every_other_form_of_deleting_a_branch(self):
        self.assert_denied(
            (
                "git push --delete origin paused/12-1",
                "git push origin -d paused/12-1",
                "git push -d origin paused/12-1",
                "git push origin :paused/12-1",
                "git push origin --delete paused/12-1 paused/12-2",
                "git push origin --delete paused/12",
                "git push origin --delete paused/x-1",
                "git push origin --delete paused/12-1-1",
                "git push origin --delete paused/12-1/x",
                "git push origin --delete paused/",
                "git push origin --delete main",
                "git push origin --delete feature/x",
                'git push origin --delete "paused/12-1"',
                "git push origin --delete paused/12-1 --force",
                "git push --force origin --delete paused/12-1",
                "git push origin --delete=paused/12-1",
                "git push upstream --delete paused/12-1",
                "git -C packages/core push origin --delete paused/12-1",
                "git push  origin  --delete paused/12-1",
                "git push origin --delete paused/12-1 # gone",
                "sudo git push origin --delete paused/12-1",
                "git push origin --delete PAUSED/12-1",
            )
        )

    def test_denies_deleting_a_paused_branch_from_a_subshell_or_a_find_action(self):
        self.assert_denied(
            (
                "(git push origin --delete paused/12-1)",
                "$(git push origin --delete paused/12-1)",
                'bash -c "git push origin --delete paused/12-1"',
                "find . -maxdepth 0 -exec git push origin --delete paused/12-1 \\;",
            ),
            expected=PUSH_NESTED_RULE,
            alternative=PUSH_NESTED_PERMITTED,
        )


class GitAliasTests(unittest.TestCase):
    def test_denies_alias_defined_by_global_option(self):
        self.assertEqual(decision(evaluate("git -c alias.s=stash s")), "deny")
        self.assertEqual(decision(evaluate("git -c alias.x='!rm -rf .' x")), "deny")
        self.assertEqual(decision(evaluate("git -calias.s=stash s")), "deny")


class GitCommitFlagTests(unittest.TestCase):
    def test_denies_all_flag(self):
        self.assertEqual(decision(evaluate('git commit -a -m "x"')), "deny")
        self.assertEqual(decision(evaluate('git commit --all -m "x"')), "deny")
        self.assertEqual(decision(evaluate('git commit -am "x"')), "deny")
        self.assertEqual(decision(evaluate('git commit -qam "x"')), "deny")

    def test_denies_no_verify(self):
        self.assertEqual(decision(evaluate('git commit --no-verify -m "x"')), "deny")
        self.assertEqual(decision(evaluate('git commit -n -m "x"')), "deny")

    def test_permits_pathspec_commit(self):
        self.assertIsNone(evaluate('git commit -m "feat(core): add thing" -- packages/core'))
        self.assertIsNone(evaluate('git commit -m "fix: x" -- packages/core'))
        self.assertIsNone(evaluate('git commit -m "docs: RFC 6749 §3.1.1" -- a'))

    def test_message_attached_to_short_flag_is_not_read_as_flags(self):
        self.assertIsNone(evaluate('git commit -m"feat: add thing" -- packages/core'))
        self.assertIsNone(evaluate('git commit -qm "feat: add thing" -- packages/core'))
        self.assertEqual(rule(evaluate("git commit -ma -- packages/core")), SUBJECT_RULE)
        result = evaluate("git commit -Fan.txt -- a")
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "git commit -F takes the message from outside the command.")

    def test_denies_commit_without_a_pathspec(self):
        for command in (
            'git commit -m "fix: x"',
            'git commit -m "fix: x" --',
            "git commit",
            "git commit -F - <<'EOF'\nfix: x\nEOF",
            "git commit -F msg.txt",
            'git commit --allow-empty -m "chore: trigger"',
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), "git commit without a pathspec commits the whole index.")
        self.assertIsNone(evaluate('git commit -m "fix: x" -- a'))
        self.assertIsNone(evaluate('git commit --allow-empty -m "chore: trigger" -- a'))

    def test_fixup_and_squash_need_a_pathspec_too(self):
        for command in ("git commit --fixup=HEAD~1", "git commit --fixup HEAD~1", "git commit --squash=HEAD~1", "git commit --squash HEAD~1"):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), "git commit without a pathspec commits the whole index.")
        self.assertIsNone(evaluate("git commit --fixup=HEAD~1 -- a"))
        self.assertIsNone(evaluate("git commit --squash HEAD~1 -- a"))


class GitCommitMessageSourceTests(unittest.TestCase):
    def test_denies_message_from_a_file(self):
        for command, flag in (
            ("git commit -F msg.txt -- a", "-F"),
            ("git commit --file=msg.txt -- a", "--file"),
            ("git commit --file msg.txt -- a", "--file"),
            ("git commit -Fmsg.txt -- a", "-F"),
            ("git commit -qF msg.txt -- a", "-F"),
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), f"git commit {flag} takes the message from outside the command.")
                self.assertEqual(permitted(result), "put the message in the command: -F - with a heredoc, or a literal -m.")

    def test_permits_stdin_message_from_a_heredoc(self):
        self.assertIsNone(evaluate("git commit -F - -- packages/core <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit --file=- -- packages/core <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit -F- -- packages/core <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<'EOF'\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a << EOF\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<EOF\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<-EOF\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a << 'EOF'\nfix: x\nEOF"))
        self.assertIsNone(evaluate('git commit -F - -- a <<"EOF"\nfix: x\nEOF'))
        self.assertIsNone(evaluate("git commit -F - -- a <<EOF # note\nfeat: x\nEOF"))


class GitCommitAttributionTests(unittest.TestCase):
    def test_denies_each_attribution_line(self):
        for line in (
            "Co-Authored-By: Claude <noreply@anthropic.com>",
            "Claude-Session: url",
            "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
            "Generated with [Claude Code](https://claude.com/claude-code)",
            "generated with [claude code]",
        ):
            with self.subTest(line=line):
                self.assertEqual(decision(evaluate(f'git commit -m "fix: thing\n\n{line}" -- packages/core')), "deny")

    def test_permits_clean_message_with_lowercase_claude_path(self):
        self.assertIsNone(evaluate('git commit -m "chore: hooks" -- .claude/hooks/x.py'))
        self.assertIsNone(evaluate('git commit -m "chore: hooks" -- .claude/hooks/git-guard.py'))


class GitCommitSubjectTests(unittest.TestCase):
    def test_denies_non_conventional_subject(self):
        for command in (
            'git commit -m "add thing" -- a',
            'git commit -m "Fixed the thing" -- a',
            'git commit -m "Feat: x" -- a',
            'git commit -m "feat:x" -- a',
            'git commit -m "feat(Core): x" -- a',
            'git commit -m "update" -- a',
            'git commit --message="Fixed the thing" -- a',
            'git commit --message "Fixed the thing" -- a',
            'git commit -qm "Fixed the thing" -- a',
            'git commit -m "Fixed the thing" -m "fix: body prose" -- a',
            "git commit -F - -- a <<'EOF'\nAdd thing\n\nbody\nEOF",
            "git commit --file=- -- a <<'EOF'\nAdd thing\nEOF",
            "git -c core.pager=cat commit -m 'Fixed' -- a",
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), SUBJECT_RULE)
                self.assertEqual(permitted(result), SUBJECT_PERMITTED)

    def test_permits_conventional_subject(self):
        for command in (
            'git commit -m "feat(core): add thing" -- a',
            'git commit -m "fix: x" -- a',
            'git commit -m "docs: RFC 6749 §3.1.1" -- a',
            'git commit -m "chore(repo): drop dependabot" -- a',
            'git commit -m "refactor(parser,lexer): share the compiler" -- a',
            'git commit -m "revert: feat(x): y" -- a',
            'git commit -m "build(deps): bump cbor2" -- a',
            'git commit -m "test(http-server): cover 409" -- a',
            'git commit --message="ci: split lanes" -- a',
            'git commit -qm "perf: x" -- a',
            'git commit -m "fix(core): x" -m "Body prose that need not be conventional." -- a',
            "git commit -F - -- a <<'EOF'\nfeat: add thing\nEOF",
            "git commit -F - -- a <<'EOF'\nfix(core): x\n\nbody\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))


class GitCommitSectionSignTests(unittest.TestCase):
    def test_denies_unqualified_section_sign(self):
        for command in (
            'git commit -m "docs: see §3.1.1" -- a',
            'git commit -m "fix: per §9.4 of the plan" -- a',
            'git commit -m "fix: x\n\nsee §2 for the shape" -- a',
            'git commit -m "fix: x" -m "see §2" -- a',
            "git commit -F - -- a <<'EOF'\nfix: x\n\nper §4.2\nEOF",
            'git commit -m "fix: RFC 6749 §3.1.1 and plan §9" -- a',
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), SECTION_RULE)
                self.assertEqual(permitted(result), SECTION_PERMITTED)

    def test_permits_qualified_section_refs(self):
        for text in ("RFC 6749 §3.1.1", "OIDC Core §3.1.2.1", "OIDC Discovery §4", "OpenID Connect §2", "RFC 9068 §2.2 and RFC 7519 §4.1.1", "RFC9052 §5.2"):
            with self.subTest(text=text):
                self.assertIsNone(evaluate(f'git commit -m "fix(core): align with {text}" -- a'))
        self.assertIsNone(evaluate('git commit -m "docs: OIDC Core §3.1.2.1" -- a'))
        self.assertIsNone(evaluate("git commit -F - -- a <<'EOF'\nfix: x\n\nRFC 6749 §3.1.1\nEOF"))


class GitPausedCommitTests(unittest.TestCase):
    PAUSED = "chore(paused): paused work for #12"

    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.root = os.path.realpath(directory.name)
        environment = {"HOME": cls.root, "XDG_CONFIG_HOME": os.path.join(cls.root, ".config"), "GIT_CONFIG_SYSTEM": os.devnull}
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.main = cls.repository("on-main", "main")
        cls.paused = cls.repository("on-paused", "paused/12-1")

    @classmethod
    def repository(cls, name, branch):
        path = os.path.join(cls.root, name)
        subprocess.run(["git", "init", "-q", "-b", branch, path], check=True, capture_output=True)
        return path

    def forms(self, subject):
        return (f'git commit -m "{subject}" -- a', f"git commit -F - -- a <<'EOF'\n{subject}\n\nRefs #12\nEOF")

    def test_denies_a_paused_commit_on_a_branch_that_is_not_paused(self):
        for command in self.forms(self.PAUSED):
            with self.subTest(command=command):
                result = evaluate(command, cwd=self.main)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), PAUSED_RULE)
                self.assertEqual(permitted(result), PAUSED_PERMITTED)

    def test_permits_a_paused_commit_on_a_paused_branch(self):
        for command in self.forms(self.PAUSED) + self.forms("chore(paused): x"):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command, cwd=self.paused))


class VerifyPipeTests(unittest.TestCase):
    def test_denies_verify_run_piped_to_a_pager(self):
        for command in (
            "npm test | tail -50",
            "npm t | tail",
            "npm test -- Core 2>&1 | tail -5",
            "npm run typecheck | head",
            "npm run test:unit | head",
            "npm run verify 2>&1 | tail -n 30",
            "npm run typecheck:strict | head -3",
            "npm run build | tail",
            "npm run lint | head",
            "npm test | tee out.txt | tail -3",
            "npm test |& tail",
            "timeout 600 npm test | tail",
            "time npm test | head",
            "nice -n 5 npm test | tail",
            "npm test | /usr/bin/tail",
            "yarn test | tail",
            "yarn t | head",
            "yarn run typecheck | head",
            "pnpm test | tail",
            "pnpm t | tail",
            "pnpm run lint | head",
            "npx jest | tail",
            "npx vitest run | tail",
            "npx mocha | head",
            "npx --yes jest | tail",
            "npx jest@29 | tail",
            "jest | tail",
            "vitest run | tail",
            "mocha | head",
            "./node_modules/.bin/jest | tail",
            "pytest | tail -20",
            "pytest tests/ -q | head",
            "python -m pytest | tail",
            "python3 -m unittest discover -s tests | tail -5",
            "python3 -m unittest | head",
            "go test ./... | tail",
            "cargo test 2>&1 | head -40",
            "cargo test | tail",
            "make test | tail",
            "make check | head",
            "make -j4 test | tail",
            "bash tests/test_apply.sh | tail -3",
            "bash ./tests/x.sh | tail",
            "bash /Users/someone/Projects/ai-config/tests/test_apply.sh | head",
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), PAGER_RULE)
                self.assertEqual(permitted(result), PAGER_PERMITTED)

    def test_permits_non_verify_pipes(self):
        for command in (
            "ls | tail",
            "git log | head",
            "git diff --stat | head -20",
            "npm ls | head",
            "npm --prefix packages/core ls | head",
            "npm run dev | head",
            "npm run start | tail",
            "yarn install | tail",
            "pnpm run dev | head",
            "npx tsc | head",
            "go build ./... | tail",
            "cargo build | head",
            "make | tail",
            "make build | head",
            "python3 script.py | tail",
            "python3 -m http.server | head",
            "bash scripts/build.sh | tail",
            "echo test | tail",
            "npm test | tee out.txt",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))


class GitCommitAmendTests(unittest.TestCase):
    def test_denies_amend(self):
        for command in ("git commit --amend --no-edit", "git commit --amend", "git commit --amend -m 'fix: x' -- a"):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), "git commit --amend rewrites an existing commit.")
                self.assertEqual(permitted(result), "make a new commit; squashing is the user's decision at review.")

    def test_all_flag_is_denied_before_amend(self):
        self.assertEqual(rule(evaluate("git commit --amend -a")), "git commit -a/--all/--no-verify commits the whole tree or skips hooks.")


class ProgramPositionTests(unittest.TestCase):
    def test_git_as_an_argument_is_not_an_invocation(self):
        self.assertIsNone(evaluate("echo git stash"))
        self.assertIsNone(evaluate('echo "git stash"'))
        self.assertIsNone(evaluate("man git stash"))
        self.assertIsNone(evaluate("grep -rn 'git stash' docs"))
        self.assertIsNone(evaluate("cat <<'EOF' > notes.md\nnever run git stash here\nEOF"))
        self.assertIsNone(evaluate("cat <<'EOF' > notes.md\ngit stash is destructive\nEOF"))

    def test_wrappers_are_stripped_before_the_program(self):
        for command in (
            "sudo git stash",
            "command git stash",
            "env git stash",
            "time git stash",
            "timeout 10 git stash",
            "timeout -k 5 10s git stash",
            "nice git stash",
            "GIT_DIR=.git git stash",
            "\\git stash",
            "/usr/bin/git stash",
            "if git stash; then echo ok; fi",
            "(git stash)",
            "{ git stash; }",
            "true & git stash",
            "xargs git stash",
            "exec git stash",
            "nohup git stash",
            "caffeinate git stash",
            "doas git stash",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")


class ShellIndirectionTests(unittest.TestCase):
    def test_denies_git_inside_shell_strings_and_substitutions(self):
        for command in (
            'eval "git stash"',
            'sh -c "git stash"',
            'bash -c "cd x && git stash"',
            'bash -lc "git stash"',
            'zsh -c "git stash"',
            'dash -c "git stash"',
            "$(git stash)",
            "echo `git stash`",
            'echo "$(git stash)"',
            'sh -c "eval \\"git stash\\""',
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")


class HeredocBodyTests(unittest.TestCase):
    def test_denies_a_command_a_shell_reads_from_a_heredoc(self):
        for command in (
            f"cat <<'EOF' | bash\nrm -rf {MONOREPO}/src\nEOF",
            "cat <<'EOF' | sh\ngit stash\nEOF",
            "cat <<'EOF' | bash -s\ngit clean -fd\nEOF",
            "cat <<'EOF' | zsh\ngit stash\nEOF",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")

    def test_permits_a_command_a_heredoc_carries_as_text(self):
        for command in (
            f"cat <<'EOF' > notes.md\nrm -rf {MONOREPO}/src\nEOF",
            "cat <<'EOF' > notes.md\nfind . -name x -delete\nEOF",
            "cat <<'EOF' > notes.md\nnpm test | tail -5\nEOF",
            f"git commit -F - -- a <<'EOF'\nfeat: x\n\nrm -rf {MONOREPO}/src is denied.\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))


class ShellReadingTests(unittest.TestCase):
    def test_an_unterminated_span_runs_to_the_end_of_the_command_and_fails_closed(self):
        for command in ("git clean -fdx $(echo", "git clean -fdx ${X", "git clean -fdx <(echo", "git clean -fdx `echo", "git clean -fdx $'x", "git clean -fdx 'x", 'git clean -fdx "x'):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), CLEAN_RULE)
        for command in ("echo $(git stash", "echo `git stash", "cat <(git stash", 'echo "$(git stash', "echo ${X:-$(git stash"):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), STASH_RULE)
        self.assertEqual(rule(evaluate("git commit -F - -- a <<'EOF\nfeat: x\nEOF")), STDIN_RULE)
        self.assertEqual(rule(evaluate("git commit -F - -- a <<$'EOF\nfeat: x\nEOF")), STDIN_RULE)


class IgnoreRepoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.root = os.path.realpath(directory.name)
        for prefix in git_guard.SAFE_RM_PREFIXES + (TMPDIR,):
            if git_guard.under_prefix(cls.root, prefix):
                raise AssertionError(f"fixture root {cls.root} lies under the safe prefix {prefix}, where every recursive rm passes")
        if "scratchpad" in cls.root.split("/"):
            raise AssertionError(f"fixture root {cls.root} carries a scratchpad segment, where every recursive rm passes")
        environment = {"TMPDIR": TMPDIR, "HOME": cls.root, "XDG_CONFIG_HOME": os.path.join(cls.root, ".config"), "GIT_CONFIG_SYSTEM": os.devnull}
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        os.makedirs(os.path.join(cls.root, "src"))
        os.makedirs(os.path.join(cls.root, "packages", "core", "dist"))
        os.symlink("src", os.path.join(cls.root, "link"))
        os.symlink(os.path.join("..", "..", "..", "src"), os.path.join(cls.root, "packages", "core", "dist", "link"))
        with open(os.path.join(cls.root, ".gitignore"), "w") as ignore:
            ignore.write(IGNORED)
        with open(os.path.join(cls.root, "src", "a.ts"), "w") as tracked:
            tracked.write("export {};\n")
        with open(os.path.join(cls.root, "notes.txt"), "w") as untracked:
            untracked.write("scratch\n")
        os.makedirs(os.path.join(cls.root, "dist"))
        with open(os.path.join(cls.root, "dist", "out.js"), "w") as ignored:
            ignored.write("export {};\n")
        os.makedirs(os.path.join(cls.root, "node_modules", "pkg"))
        os.symlink(os.path.dirname(cls.root), os.path.join(cls.root, "escape"))
        with open(os.path.join(cls.root, "build"), "w") as tracked_file_under_a_directory_pattern:
            tracked_file_under_a_directory_pattern.write("#!/bin/sh\n")
        with open(os.path.join(cls.root, "-x"), "w") as dash_named:
            dash_named.write("x\n")
        os.makedirs(os.path.join(cls.root, "packages", "foo", "build"))
        with open(os.path.join(cls.root, "packages", "foo", "build", "index.ts"), "w") as tracked_under_a_directory_named_by_an_anchored_pattern:
            tracked_under_a_directory_named_by_an_anchored_pattern.write("export {};\n")
        cls.git("init", "-q")
        cls.git("config", "user.email", "fixture@example.invalid")
        cls.git("config", "user.name", "fixture")
        cls.git("add", "--", ".gitignore", "src/a.ts", "build", "packages/foo/build/index.ts")
        cls.git("commit", "-q", "-m", "chore: fixture", "--", ".gitignore", "src/a.ts", "build", "packages/foo/build/index.ts")

    @classmethod
    def git(cls, *args):
        subprocess.run(["git", "-C", cls.root, *args], check=True, capture_output=True)

    def in_repo(self, command, path=""):
        return evaluate(command, cwd=os.path.join(self.root, path))

    def outside_repo(self):
        return tempfile.TemporaryDirectory(dir=os.path.dirname(self.root))


class RmTests(IgnoreRepoTests):
    def test_permits_recursive_rm_of_a_git_ignored_path(self):
        for command in (
            "rm -rf node_modules",
            "rm -rf ./dist",
            "rm -rf dist/",
            "rm -rf packages/core/dist",
            "rm -rf packages/core/dist/bundle.js",
            "rm -rf node_modules dist",
            f"rm -rf {self.root}/node_modules",
            "sudo rm -rf node_modules",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

    def test_denies_rm_of_a_tracked_file_whose_name_matches_a_directory_pattern(self):
        for command in ("rm build", "rm -f build", "rm -rf build"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)

    def test_targets_after_double_dash_are_judged(self):
        for command in ("rm -- -x", "rm -rf -- -x", "rm -f -- src/a.ts -x"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("rm -f -- dist/out.js"))

    def test_denies_glob_target(self):
        for command in ("rm *.log", "rm -rf build*", "rm -rf dist/[ab]", "rm -rf dist/?", "find 'dist/*' -delete"):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), SUBSTITUTION_RULE)
                self.assertEqual(permitted(result), "name the path literally.")
        self.assertIsNone(self.in_repo("rm -rf node_modules"))

    def test_ignored_path_is_resolved_against_a_subdirectory_cwd(self):
        self.assertIsNone(self.in_repo("rm -rf dist", "packages/core"))
        self.assertIsNone(self.in_repo("rm -rf ../../node_modules", "packages/core"))
        self.assertEqual(rule(self.in_repo("rm -rf .", "packages/core")), RM_RULE)
        self.assertEqual(rule(self.in_repo("rm -rf ../../src", "packages/core")), RM_RULE)

    def test_denies_recursive_rm_of_a_path_git_does_not_ignore(self):
        for command in (
            "rm -rf src",
            "rm -rf src/a.ts",
            "rm -R build",
            "rm -fr ./x",
            "rm -rf node_modules src",
            "rm -rf $TMPDIR/x ./y",
            "rm -rf ./scratchpad/x",
            "rm -rf scratchpad",
            "rm -rf /a/scratchpad-old/x",
        ):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), RM_RULE)
                self.assertTrue(permitted(result).startswith("mv "))

    def test_denies_recursive_rm_of_an_ignored_symlink(self):
        for command in ("rm -rf link/", "rm -rf link", "rm -rf ./link/", f"rm -rf {self.root}/link/", "rm -rf packages/core/dist/link/"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)

    def test_denies_recursive_rm_of_the_repository_root(self):
        for command, path in (
            ("rm -rf .", ""),
            ("rm -rf ./", ""),
            (f"rm -rf {self.root}", ""),
            (f"rm -rf {self.root}/", ""),
            ("rm -rf ../..", "packages/core"),
            (f"rm -rf {self.root}", "packages/core"),
        ):
            with self.subTest(command=command, path=path):
                self.assertEqual(rule(self.in_repo(command, path)), RM_RULE)

    def test_denies_recursive_rm_outside_the_repository(self):
        with self.outside_repo() as outside:
            self.assertEqual(rule(evaluate("rm -rf node_modules", cwd=outside)), RM_RULE)
            self.assertEqual(rule(self.in_repo(f"rm -rf {outside}/node_modules")), RM_RULE)
        self.assertEqual(rule(self.in_repo("rm -rf ../x")), RM_RULE)
        self.assertEqual(rule(self.in_repo("rm -rf /Users/nobody/node_modules")), RM_RULE)
        self.assertEqual(rule(git_guard.evaluate({"tool_name": "Bash", "tool_input": {"command": "rm -rf node_modules"}})), RM_RULE)

    def test_denies_rm_by_path_or_wrapper(self):
        for command in ("sudo rm -rf x", "/bin/rm -rf x", "command rm -rf x", "timeout 5 rm -rf x", "echo $(rm -rf build)", "sudo rm x", "/bin/rm x"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)

    def test_denies_when_target_escapes_temp(self):
        for command in ("rm -rf $TMPDIR/../../../etc", 'rm -rf "${TMPDIR}/../x"', "rm -rf /tmp/claude/../etc"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)

    def test_denies_a_target_the_guard_cannot_resolve(self):
        for command in (
            'rm -rf "$TMPDIR/$(echo ../..)"',
            'rm -rf "$TMPDIR/`echo ../..`"',
            'rm -rf "${TMPDIR:-/}/x"',
            'rm -rf "${TMPDIR}/${X}"',
            'rm -rf "$TMPDIR/${X}"',
            "rm -rf /tmp/claude/$(basename $PWD)",
            "rm -rf node_modules/$(x)",
            "rm -rf ~/node_modules",
            "rm -rf ~/Documents/x",
            "rm -rf $HOME/dist",
            "rm -rf $X/node_modules",
            "rm -rf ~",
            'rm -rf "$HOME/node_modules"',
            "rm -rf $TMPDIRX/x",
            "rm -rf node_modules ~/dist",
            "rm -- ~/x",
            "rm $HOME/x",
            "rm $(f)",
        ):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), SUBSTITUTION_RULE)
                self.assertEqual(permitted(result), "name the path literally.")

    def test_denies_when_target_only_shares_a_prefix_string(self):
        for command in ("rm -rf /tmp/claudeX", "rm -rf /private/tmp/claude-evil/x", f"rm -rf {TMPDIR}-evil/x"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)

    def test_permits_recursive_rm_under_temp(self):
        self.assertIsNone(self.in_repo("rm -rf $TMPDIR/out"))
        self.assertIsNone(self.in_repo('rm -rf "$TMPDIR/x"'))
        self.assertIsNone(self.in_repo('rm -rf "${TMPDIR}/x"'))
        self.assertIsNone(self.in_repo("rm -rf /tmp/claude/x /private/tmp/claude/y"))
        self.assertIsNone(self.in_repo("rm -rf /tmp/claude"))
        self.assertIsNone(self.in_repo("rm -rf /some/where/scratchpad/x"))
        self.assertIsNone(self.in_repo("rm -rf /some/where/scratchpad"))

    def test_denies_plain_rm_of_a_path_git_does_not_ignore(self):
        for command in ("rm -f packages/core/src/x.ts", "rm src/a.ts", "rm notes.txt", "rm -- src/a.ts", "rm node_modules src/a.ts", "rm dist/out.js notes.txt"):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), RM_RULE)
                self.assertTrue(permitted(result).startswith("mv "))

    def test_permits_plain_rm_of_a_git_ignored_or_temp_path(self):
        for command in ("rm -f dist/out.js", "rm dist/out.js", 'rm "$TMPDIR/x"', "rm -- packages/core/dist/bundle.js", "rm -f dist/out.js packages/core/dist/bundle.js"):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

    def test_denies_rm_behind_an_absolute_path_wrapper(self):
        for command in ("/usr/bin/nice -n 5 rm -rf src", "/usr/bin/sudo rm src/a.ts", "/usr/bin/env rm notes.txt", "/usr/bin/timeout 5 /bin/rm -rf src"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("/usr/bin/nice -n 5 rm -rf node_modules"))

    def test_denies_rm_fed_by_xargs(self):
        for command in ("ls | xargs rm -rf", "xargs rm", "find . -name '*.log' | xargs rm -f", "xargs -0 rm -rf", "xargs -n1 rm", "sudo xargs rm -f"):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), SUBSTITUTION_RULE)
                self.assertEqual(permitted(result), "name the path literally.")
        self.assertIsNone(self.in_repo("xargs -n1 echo"))
        self.assertIsNone(self.in_repo("ls | xargs -I {} echo {}"))

    def test_git_absent_timed_out_or_failing_means_not_ignored(self):
        for outcome in (FileNotFoundError(2, "git"), subprocess.TimeoutExpired(["git"], 5), mock.Mock(returncode=128, stdout=b".gitignore\x001\x00node_modules/\x00node_modules\x00")):
            with self.subTest(outcome=outcome):
                patch = {"side_effect": outcome} if isinstance(outcome, BaseException) else {"return_value": outcome}
                with mock.patch.object(git_guard.subprocess, "run", **patch):
                    self.assertEqual(rule(self.in_repo("rm -rf node_modules")), RM_RULE)

    def test_a_negated_pattern_does_not_make_a_path_deletable(self):
        for command in ("rm keep.log", "rm -rf keep.log", "rm -f other.log keep.log"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("rm other.log"))

    def test_budget_exhaustion_denies_with_the_budget_reason(self):
        answer = mock.Mock(returncode=0, stdout=b".gitignore\x002\x00dist/\x00dist\x00")
        with mock.patch.object(git_guard.subprocess, "run", return_value=answer) as run, mock.patch.object(git_guard.time, "monotonic", side_effect=itertools.count(0, 3)):
            result = self.in_repo("rm -rf dist; rm -rf dist; rm -rf dist; rm -rf dist")
        self.assertEqual(rule(result), BUDGET_RULE)
        self.assertTrue(permitted(result).startswith("fewer"))
        self.assertLess(run.call_count, 4)

    def test_a_stalled_git_denies_inside_the_budget(self):
        command = "; ".join(f"rm -rf dist{index}" for index in range(20))
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "git"), "w") as script:
                script.write(FAKE_GIT)
            os.chmod(os.path.join(directory, "git"), 0o755)
            path = directory + os.pathsep + os.environ["PATH"]
            with mock.patch.dict(os.environ, {"PATH": path, "FAKE_GIT_SLEEP": "1"}):
                started = time.monotonic()
                result = self.in_repo(command)
                elapsed = time.monotonic() - started
            with mock.patch.dict(os.environ, {"PATH": path, "FAKE_GIT_SLEEP": "0"}):
                self.assertIsNone(self.in_repo(command))
        self.assertEqual(rule(result), BUDGET_RULE)
        self.assertLess(elapsed, 9)


class FindDeleteTests(IgnoreRepoTests):
    def test_permits_ignored_names_with_allowed_primaries_and_one_action(self):
        for command, path in (
            ("find . -name '*.pyc' -delete", ""),
            ("find . -type d -name __pycache__ -exec rm -rf {} +", ""),
            ("find . -type d -name node_modules -prune -exec rm -rf {} +", ""),
            ("find . -maxdepth 2 -type d -name dist -prune -exec rm -rf {} +", ""),
            ("find . -mindepth 1 -type f -name '*.pyc' -print -delete", ""),
            ("find . -name '*.pyc' -print0 -delete", ""),
            ("find . -name '*.pyc' -execdir rm {} +", ""),
            ("find packages -type d -name dist -exec rm -rf {} +", ""),
            ("find . -type d -path '*/node_modules' -prune -exec rm -rf {} +", ""),
            ("find . -path '*/dist/*' -delete", ""),
            ("find src -name '*.pyc' -delete", ""),
            ("find . -type d -name '*.pyc' -name __pycache__ -delete", ""),
            ("find . -name '*.pyc' -delete", "packages/core"),
            ("find ../.. -name '*.pyc' -delete", "packages/core"),
        ):
            with self.subTest(command=command, path=path):
                self.assertIsNone(self.in_repo(command, path))

    def test_denies_a_deleting_find_whose_name_git_does_not_ignore(self):
        for command in (
            "find . -name '*.js' -delete",
            "find -name '*.js' -delete",
            "find . -name '*.ts' -delete",
            "find . -name '*.pyc' -name '*.ts' -delete",
            "find . -path '*/src/*' -delete",
            "find packages -type d -name src -exec rm -rf {} +",
            "find packages -type d -name src -exec rm -r {} \\;",
            "find . -type d -name src -execdir rm -fr {} +",
            "find . -type d -name src -exec rm -R {} +",
            "find -L packages -name src -delete",
            "find . -delete",
            "find src -delete",
            "find . -type d -delete",
            "find $TMPDIR/x . -delete",
            "find $TMPDIR/x . -name '*.pyc' -delete",
        ):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), RM_RULE)
                self.assertTrue(permitted(result).startswith("mv "))

    def test_denies_primaries_operators_and_actions_outside_the_shape(self):
        for command in (
            "find . -name '*.pyc' -o -name x -delete",
            "find . -name '*.pyc' -o -delete",
            "find . -name '*.pyc' -or -delete",
            "find . ! -name x -delete",
            "find . ! -name '*.pyc' -delete",
            "find . -not -name '*.pyc' -delete",
            "find . \\( -name '*.pyc' \\) -delete",
            "find . -name '*.pyc' -a -name y -delete",
            "find . -name '*.pyc' -a -type f -delete",
            "find . -name '*.pyc' -and -type f -delete",
            "find . -name '*.pyc' -newer y -delete",
            "find . -name '*.pyc' -mtime +7 -delete",
            "find . -name '*.pyc' -size +1k -delete",
            "find . -name '*.pyc' -empty -delete",
            "find . -type l -name '*.pyc' -delete",
            "find . -maxdepth x -name '*.pyc' -delete",
            "find . -iname '*.PYC' -delete",
            "find . -iname '*.pyc' -delete",
            "find . -type d -ipath '*/__pycache__' -exec rm -r {} \\;",
            "find . -name '*.pyc' -delete -delete",
            "find . -name '*.pyc' -exec rm {} \\; -delete",
            "find . -name '*.pyc' -delete -type d",
            "find . -name build -delete -type d",
            "find . -name build -exec rm -rf {} + -type d",
            "find . -type d -o -name build -delete",
            "find . -type d -or -name build -delete",
            "find . ! -type d -name build -delete",
            "find . -not -type d -name build -delete",
            "find . \\( -type d \\) -name build -delete",
        ):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), RM_RULE)
                self.assertTrue(permitted(result).startswith("mv "))

    def test_denies_a_deleting_find_whose_start_path_is_outside_the_repository(self):
        for command in (
            "find / -name '*.pyc' -delete",
            "find ../other -name '*.pyc' -delete",
            "find /Users/nobody -name '*.pyc' -delete",
            f"find {os.path.dirname(self.root)} -name '*.pyc' -delete",
            "find . ../other -name '*.pyc' -delete",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        with self.outside_repo() as outside:
            self.assertEqual(rule(evaluate("find . -name '*.pyc' -delete", cwd=outside)), RM_RULE)

    def test_git_run_by_an_action_is_judged_by_the_git_rules(self):
        stash = "git stash silently destroys uncommitted work in a shared tree."
        clean = CLEAN_RULE
        for command, expected in (
            ("find . -maxdepth 0 -exec git stash \\;", stash),
            ("find . -exec git clean -fdx \\;", clean),
            ("find node_modules -execdir git stash \\;", stash),
            ("find . -name '*.pyc' -ok git clean -fdx \\;", clean),
            ("find . -okdir git stash \\;", stash),
            ("find . -exec sh -c 'git stash' \\;", stash),
            ("find . -exec sudo git clean -fdx \\;", clean),
            ("find . -name '*.ts' -exec git stash \\; -delete", stash),
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), expected)
        self.assertIsNone(self.in_repo("find . -exec git status \\;"))
        self.assertIsNone(self.in_repo("find . -name '*.ts' -exec git add -- {} +"))

    def test_denies_a_start_path_or_name_value_with_a_substitution(self):
        for command in (
            'find "$TMPDIR/$(echo ../..)" -delete',
            'find "$(pwd)" -name \'*.pyc\' -delete',
            "find ~/node_modules -delete",
            "find $HOME -name '*.pyc' -delete",
            "find $DIR -delete",
            'find . -name "$PAT" -delete',
            'find . -name "${PAT}" -delete',
            'find . -name "`cat p`" -delete',
            'find . -name "$(cat p)" -delete',
            "find . -path '$X/*.pyc' -delete",
            "find . -name '~*.pyc' -delete",
            'find . -type d -name "$D" -exec rm -rf {} +',
        ):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), SUBSTITUTION_RULE)
                self.assertEqual(permitted(result), "name the path literally.")

    def test_find_exec_reaching_rm_through_a_shell_or_wrapper_is_a_delete(self):
        for command, expected in (
            ("find . -name '*.ts' -exec sh -c 'rm -rf \"$1\"' _ {} \\;", SUBSTITUTION_RULE),
            ("find . -name '*.ts' -exec bash -c 'rm $0' {} \\;", SUBSTITUTION_RULE),
            ("find . -name '*.ts' -exec xargs rm {} +", SUBSTITUTION_RULE),
            ("find . -name '*.pyc' -ok sh -c 'rm $1' _ {} \\;", SUBSTITUTION_RULE),
            ("find . -name '*.ts' -execdir sudo rm {} \\;", RM_RULE),
            ("find . -name '*.ts' -exec /usr/bin/env rm -f {} +", RM_RULE),
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), expected)
        self.assertIsNone(self.in_repo("find . -name '*.ts' -exec sh -c 'cat \"$1\"' _ {} \\;"))

    def test_the_action_rm_may_target_only_the_match_or_a_deletable_path(self):
        for command in (
            "find . -name '*.pyc' -exec rm -rf src \\;",
            "find . -name '*.pyc' -exec rm -rf {} ../src \\;",
            "find . -name '*.pyc' -exec sh -c 'rm -rf src' \\;",
            "find . -name '*.pyc' -execdir rm -rf / \\;",
            "find . -type d -name __pycache__ -exec rm -rf {} notes.txt +",
            "find node_modules -exec rm -rf src \\;",
            'find "$TMPDIR/x" -exec rm -rf {} src/a.ts \\;',
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        for command in (
            "find . -name '*.pyc' -exec sh -c 'rm $1' _ {} \\;",
            "find . -name '*.pyc' -exec sh -c 'rm -f \"$1\"' _ {} \\;",
            "find . -name '*.pyc' -exec bash -c 'rm $0' {} \\;",
            "find . -name '*.pyc' -exec xargs rm {} +",
            "find node_modules -exec rm -rf {} $X \\;",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), SUBSTITUTION_RULE)
        for command in (
            "find . -name '*.pyc' -exec rm -rf {} +",
            "find . -name '*.pyc' -exec rm -f -- {} \\;",
            "find . -name '*.pyc' -exec rm -rf {} dist \\;",
            "find . -name '*.pyc' -exec sh -c 'rm -rf \"$TMPDIR/x\"' \\;",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

    def test_denies_a_deleting_find_that_follows_links_whatever_the_start_path(self):
        for command in (
            "find -L /tmp/claude/x -delete",
            'find -L "$TMPDIR/x" -delete',
            "find -L node_modules -type f -exec rm {} +",
            "find -H node_modules -delete",
            "find -L escape -name '*.pyc' -delete",
            "find -H escape -name '*.pyc' -delete",
            "find -L . -name '*.pyc' -delete",
            "find -H -f node_modules -delete",
        ):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), RM_RULE)
                self.assertTrue(permitted(result).startswith("mv "))
        for command in (
            "find -P . -name '*.pyc' -delete",
            "find -P /tmp/claude/x -delete",
            "find -L . -name '*.ts' -exec cat {} +",
            "find -L /tmp/claude/x -name x",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

    def test_git_commit_inside_an_action_cannot_be_judged(self):
        result = self.in_repo("find . -exec git commit -m 'x' -- src/a.ts \\;")
        self.assertEqual(rule(result), "git commit inside a find action cannot be judged.")
        self.assertEqual(permitted(result), "run git commit as its own command with -- <paths>.")
        self.assertEqual(rule(self.in_repo("find . -exec sh -c 'git commit -m \"fix: x\" -- src/a.ts' \\;")), "git commit inside a find action cannot be judged.")
        self.assertEqual(rule(self.in_repo("find . -exec git commit -a -m 'x' \\;")), "git commit -a/--all/--no-verify commits the whole tree or skips hooks.")

    def test_git_checkout_or_restore_of_the_match_inside_an_action_cannot_be_judged(self):
        for subcommand in ("checkout", "restore"):
            with self.subTest(subcommand=subcommand):
                result = self.in_repo(f"find . -type f -exec git {subcommand} -- {{}} +")
                self.assertEqual(rule(result), f"git {subcommand} inside a find action cannot be judged.")
                self.assertEqual(permitted(result), f"run git {subcommand} as its own command with -- <paths>.")
                self.assertEqual(rule(self.in_repo(f"find . -exec sh -c 'git {subcommand} -- {{}}' \\;")), f"git {subcommand} inside a find action cannot be judged.")
        self.assertEqual(rule(self.in_repo("find . -exec git checkout -- . \\;")), "tree-wide git checkout pathspec reverts everyone's uncommitted work.")
        self.assertEqual(rule(self.in_repo("find . -exec git restore {} \\;")), "tree-wide git restore reverts everyone's uncommitted work.")
        self.assertIsNone(self.in_repo("find . -exec git checkout -- src/a.ts \\;"))

    def test_execdir_targets_run_from_the_match_and_the_match_is_only_ever_bare(self):
        for command in (
            "find . -name '*.pyc' -execdir rm -rf build \\;",
            "find . -name '*.pyc' -execdir rm -rf dist \\;",
            "find node_modules -execdir rm -rf dist \\;",
            "find . -name '*.pyc' -execdir rm -rf {} dist \\;",
            "find . -name '*.pyc' -exec rm -rf {}/../dist +",
            "find . -name '*.pyc' -exec rm -rf {}.bak \\;",
            "find . -name '*.pyc' -execdir rm -rf {}/x \\;",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo('find . -name \'*.pyc\' -execdir rm -rf "$TMPDIR/x" \\;'))
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -execdir rm -rf /tmp/claude/x {} \\;"))
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -exec rm -rf {} dist \\;"))

    def test_find_exec_rm_with_any_flags_is_a_delete(self):
        for command in ("find src -name a.ts -exec rm -f {} +", "find . -name '*.ts' -exec rm {} \\;", "find . -name '*.js' -exec rm -f {} +", "find src -execdir rm {} +"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -exec rm -f {} +"))
        self.assertIsNone(self.in_repo("find . -name '*.ts' -exec cat {} +"))

    def test_permits_find_that_does_not_delete(self):
        self.assertIsNone(self.in_repo("find . -name '*.ts' -newer x"))
        self.assertIsNone(self.in_repo("find . -exec grep -l foo {} \\;"))
        self.assertIsNone(self.in_repo("find . -type f -print0"))
        self.assertIsNone(self.in_repo("find . -name '*.ts' -exec cat {} +"))


class CompoundCommandTests(unittest.TestCase):
    def test_denies_stash_after_and(self):
        self.assertEqual(decision(evaluate("cd packages/core && npm test && git stash")), "deny")

    def test_denies_stash_after_semicolon_and_pipe(self):
        self.assertEqual(decision(evaluate("ls; git stash")), "deny")
        self.assertEqual(decision(evaluate("echo x | git stash")), "deny")
        self.assertEqual(decision(evaluate("true || git reset --hard")), "deny")
        self.assertEqual(decision(evaluate("ls | xargs git stash")), "deny")

    def test_permits_safe_compound(self):
        self.assertIsNone(evaluate("cd packages/core && git status && git diff --stat | head -20"))
        self.assertIsNone(evaluate('npm test > "$TMPDIR/o.txt" 2>&1; tail -50 "$TMPDIR/o.txt"'))
        self.assertIsNone(evaluate("npm test && tail out.txt"))
        self.assertIsNone(evaluate("if git diff --quiet; then echo clean; fi"))
        self.assertIsNone(evaluate('for f in a b; do git add -- "$f"; done'))

    def test_handles_git_global_options(self):
        self.assertEqual(decision(evaluate("git -C example-monorepo stash")), "deny")
        self.assertEqual(decision(evaluate("git -c core.pager=cat stash")), "deny")
        self.assertEqual(decision(evaluate("git --no-pager --git-dir=.git stash")), "deny")


class ScannerTests(unittest.TestCase):
    def test_random_text_scans_without_raising_and_tiles(self):
        alphabet = "ab rm-$(){}[]'\"`\\<>|&;#\n\t~*?=:.,/x0"
        generator = random.Random(23)
        for _ in range(2000):
            text = "".join(generator.choice(alphabet) for _ in range(generator.randrange(40)))
            with self.subTest(text=text):
                starts, ends = [span.start for span in git_guard.spans(text)], [span.end for span in git_guard.spans(text)]
                self.assertEqual(starts, [0] + ends[:-1] if ends else [])
                self.assertEqual(ends[-1:], [len(text)] if text else [])
                self.assertIn(decision(evaluate(text, cwd="")), {None, "deny"})


class GhRepoFlagTests(unittest.TestCase):
    def test_denies_a_repo_flag_quoted_together_with_its_value(self):
        for command in (
            'gh issue comment 5 "--repo owner/name" --body x',
            "gh issue comment 5 '--repo owner/name' --body x",
            'gh issue view 5 "--repo=owner/name "',
            'gh issue view 5 "--repo= owner/name"',
            "gh issue view 5 --repo\\ owner/name",
            'gh "--repo owner/name" issue view 5',
            'timeout 30 gh issue list "--repo owner/name"',
            'echo $(gh issue view 5 "--repo owner/name")',
            'git status && gh issue edit 5 --add-label question "--repo owner/name"',
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), GH_REPO_RULE)
                self.assertEqual(permitted(result), GH_REPO_PERMITTED)

    def test_permits_the_repo_flag_as_two_words_or_joined_to_its_value(self):
        for command in (
            "gh issue comment 5 --repo owner/name --body x",
            "gh issue view 5 --repo=owner/name",
            "gh --repo owner/name issue view 5",
            "gh issue edit 5 --add-label question --remove-label ready --repo owner/name",
            "gh issue view 5 --json comments --jq '.comments[].body' --repo owner/name",
            'gh label edit question --description "An unanswered ## Question comment: out of the queue until its ## Ruling is posted" --repo owner/name',
            'echo "--repo owner/name"',
            'git log --oneline -- "--repo owner/name"',
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))


class GhGuardTests(unittest.TestCase):
    def assert_denied(self, command, expected, alternative, cwd=MONOREPO):
        result = evaluate(command, cwd)
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), expected)
        self.assertEqual(permitted(result), alternative)

    def assert_unreadable_text(self, command, flag, subcommand="create", cwd=MONOREPO):
        self.assert_denied(command, f"gh pr {subcommand} {flag} carries text the guard cannot read.", GH_TEXT_PERMITTED, cwd)

    def directory_with(self, files):
        """A fresh directory holding each name → bytes of files, resolved for the payload cwd."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = os.path.realpath(directory.name)
        for name, content in files.items():
            with open(os.path.join(root, name), "wb") as handle:
                handle.write(content)
        return root


class GhMergeTests(GhGuardTests):
    def test_denies_gh_pr_merge_in_every_form(self):
        for command in ("gh pr merge 12", "gh pr merge 12 --auto --rebase", "gh pr merge --squash --delete-branch 12", "timeout 30 gh pr merge 12"):
            with self.subTest(command=command):
                self.assert_denied(command, GH_MERGE_RULE, GH_MERGE_PERMITTED)

    def test_denies_gh_api_on_a_pull_merge_merge_async_or_update_branch_path_whatever_its_number_or_query_string(self):
        for command in (
            "gh api -X PUT repos/o/n/pulls/12/merge",
            "gh api -X PUT 'repos/o/n/pulls/12/merge?x=1'",
            "gh api -X PUT repos/o/n/pulls/12/update-branch",
            "gh api -X PUT repos/o/n/pulls/12/merge-async",
            'gh api -X PUT "repos/o/n/pulls/$PR/merge"',
        ):
            with self.subTest(command=command):
                self.assert_denied(command, GH_MERGE_RULE, GH_MERGE_PERMITTED)

    def test_denies_gh_api_graphql_text_carrying_a_merge_auto_merge_enqueue_or_update_branch_mutation(self):
        for command in (
            "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
            "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
            "gh api graphql -f query='mutation { updatePullRequestBranch(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
            "gh api graphql -f query='mutation { enqueuePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
        ):
            with self.subTest(command=command):
                self.assert_denied(command, GH_MERGE_RULE, GH_MERGE_PERMITTED)

    def test_permits_reading_and_listing_pull_requests(self):
        for command in ("gh pr view 12 --json state", "gh pr list --state open --head feature/x", "gh api repos/o/n/pulls/12 --jq .state"):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))


class GhAliasTests(GhGuardTests):
    def test_denies_gh_alias_set_and_import_in_every_form(self):
        for command in ("gh alias set pm 'pr merge'", "gh alias set --shell m '!gh pr merge $1'", "gh alias import aliases.yml", "gh alias import -"):
            with self.subTest(command=command):
                self.assert_denied(command, GH_ALIAS_RULE, GH_ALIAS_PERMITTED)


class GhApiBodyTests(GhGuardTests):
    def test_denies_a_graphql_or_pulls_body_read_from_a_file_or_stdin(self):
        for command in (
            "gh api graphql --input q.json",
            "gh api graphql --input -",
            "gh api graphql -F query=@merge.graphql",
            "gh api graphql --field query=@-",
            "gh api repos/o/n/pulls/12 --input body.json",
        ):
            with self.subTest(command=command):
                self.assert_denied(command, GH_API_BODY_RULE, GH_API_BODY_PERMITTED)
        self.assert_denied("gh api -X PUT repos/o/n/pulls/12/merge -F commit_title=@t.txt", GH_MERGE_RULE, GH_MERGE_PERMITTED)


class GhPrClosingKeywordTests(GhGuardTests):
    def test_denies_a_closing_keyword_before_an_issue_reference_in_any_title_body_or_attach_text(self):
        for command in (
            "gh pr create -t t -b 'Closes #58'",
            "gh pr create --title t --body 'Closes #58'",
            "gh pr create --title=t --body='Fixes OWNER/REPO#58'",
            "gh pr create -t t -b 'Fixes " + "o" * 39 + "/" + "r" * 100 + "#58'",
            "gh pr create -t t -b 'Fixes " + "o" * 100 + "/" + "r" * 100 + "#58'",
            "gh pr create -t t -b 'Resolves https://github.com/o/n/issues/58'",
            "gh pr create -t 'fix: x, resolves #58' -b b",
            "gh pr edit 12 --body 'Fixes #58'",
            "gh pr create -t t -b b --attach './a.png#Closes #58'",
        ):
            with self.subTest(command=command):
                self.assert_denied(command, GH_CLOSING_RULE, GH_CLOSING_PERMITTED)

    def test_permits_refs_before_an_issue_reference(self):
        self.assertIsNone(evaluate("gh pr create --title t --body 'Refs #58'"))


class GhPrUnreadableTextTests(GhGuardTests):
    def test_denies_fill_template_editor_web_and_recover(self):
        for command, flag in (
            ("gh pr create --fill", "--fill"),
            ("gh pr create -f", "-f"),
            ("gh pr create --fill-first", "--fill-first"),
            ("gh pr create --fill-verbose", "--fill-verbose"),
            ("gh pr create -t t -T pull_request_template.md", "-T"),
            ("gh pr create -e", "-e"),
            ("gh pr create -w", "-w"),
            ("gh pr create --recover r.json", "--recover"),
        ):
            with self.subTest(command=command):
                self.assert_unreadable_text(command, flag)

    def test_denies_a_body_file_it_cannot_resolve_open_or_decode_and_raises_nothing(self):
        for cwd in (self.directory_with({}), self.directory_with({"f": b"\xff\xfe"}), ""):
            with self.subTest(cwd=cwd):
                self.assert_unreadable_text("gh pr create -t t -F f", "-F", cwd=cwd)


class GhPermittedCommandsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        root = os.path.realpath(directory.name)
        environment = {"HOME": root, "XDG_CONFIG_HOME": os.path.join(root, ".config"), "GIT_CONFIG_SYSTEM": os.devnull}
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.paused = os.path.join(root, "paused")
        subprocess.run(["git", "init", "-q", "-b", "paused/12-1", cls.paused], check=True, capture_output=True)

    def test_permits_every_issue_pr_read_push_pause_and_graphql_command_the_tree_runs_from_a_paused_branch(self):
        for command in (
            'gh issue close 58 --comment "abc1234 feat(x): y"',
            "gh issue comment 58 --body-file f.md",
            "gh pr view 12 --json state",
            "gh pr list --state open --head feature/x",
            "git push origin feature/x",
            "git push origin --delete paused/58-1",
            "gh api graphql -f query='query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issue(number:58){blockedBy(first:50){nodes{number state}} subIssues(first:50){nodes{number state}}}}}' -F owner=o -F name=n",
            "gh api graphql -f query='mutation { addSubIssue(input: {issueId: \"I_1\", subIssueId: \"I_2\"}) { issue { number } subIssue { number } } }'",
            "gh api graphql -f query='mutation { addBlockedBy(input: {issueId: \"I_1\", blockingIssueId: \"I_2\"}) { issue { number } blockingIssue { number } } }'",
            "git check-ignore -q .tmp/",
            "git switch -c paused/12-1",
            "git add -- a",
            "git commit -F - -- a <<'EOF'\nchore(paused): paused work for #12\n\nWorking branch: main. Done: the helper. Next step: its test.\n\nRefs #12\nEOF",
            "git push origin paused/12-1",
            "git switch main",
            "gh issue comment 12 --body-file paused.md",
            "gh issue edit 12 --add-label paused --remove-label ready",
            "git fetch origin paused/12-1:paused/12-1",
            "git cherry-pick --no-commit paused/12-1",
            "git branch -D paused/12-1",
            "git branch --list 'paused/12-*'",
            "git push origin --delete paused/12-1",
            "git ls-remote origin 'refs/heads/paused/12-*'",
            "git push origin feature/93-push",
            "git push origin main",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command, cwd=self.paused))


class FailOpenTests(unittest.TestCase):
    def test_ignores_other_tools(self):
        self.assertIsNone(git_guard.evaluate({"tool_name": "Edit", "tool_input": {"file_path": "x"}}))

    def test_missing_fields_raise_and_main_stays_silent(self):
        for garbage in ("", "not json", '{"tool_name": "Bash"}', '{"tool_name": "Bash", "tool_input": {}}', "[]"):
            with self.subTest(garbage=garbage):
                out = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO(garbage)), redirect_stdout(out):
                    with self.assertRaises(SystemExit) as raised:
                        git_guard.main()
                self.assertEqual(raised.exception.code, 0)
                self.assertEqual(out.getvalue(), "")

    def test_non_string_command_is_ignored(self):
        self.assertIsNone(evaluate(None))

    def test_missing_cwd_is_tolerated(self):
        self.assertEqual(decision(git_guard.evaluate({"tool_name": "Bash", "tool_input": {"command": "git checkout -- ."}})), "deny")
        self.assertIsNone(git_guard.evaluate({"tool_name": "Bash", "tool_input": {"command": "git checkout -- src"}}))


class SubprocessTests(unittest.TestCase):
    def test_denies_via_stdin_and_exits_zero(self):
        proc = subprocess.run([sys.executable, HOOK_PATH], input=json.dumps(bash("git stash")), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
