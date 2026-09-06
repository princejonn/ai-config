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

MONOREPO = "/Users/jonn/Projects/lindorm/lindorm-monorepo"
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
        self.assertIsNone(evaluate("git reset HEAD -- packages/aegis/src/x.ts"))

    def test_denies_clean(self):
        self.assertEqual(decision(evaluate("git clean -fdx")), "deny")


class GitCheckoutRestoreSwitchTests(unittest.TestCase):
    def test_denies_tree_wide_checkout(self):
        self.assertEqual(decision(evaluate("git checkout .")), "deny")
        self.assertEqual(decision(evaluate("git checkout main")), "deny")

    def test_permits_branch_creation(self):
        self.assertIsNone(evaluate("git checkout -b feat/x"))
        self.assertIsNone(evaluate("git checkout -B feat/x"))
        self.assertIsNone(evaluate("git checkout -b feat"))

    def test_permits_pathspec_scoped_checkout(self):
        self.assertIsNone(evaluate("git checkout -- packages/aegis/src/a.ts"))
        self.assertIsNone(evaluate("git checkout HEAD -- packages/aegis/src/a.ts"))
        self.assertIsNone(evaluate("git checkout -- path/to/file"))

    def test_denies_tree_wide_pathspec_after_double_dash(self):
        for spec in (".", "./", ":/", "*", "':(top)'", ":/src", "./.", ":", "'**'", "..", "../..", "$PWD", "${PWD}", "$PWD/"):
            for subcommand in ("checkout", "restore"):
                with self.subTest(subcommand=subcommand, spec=spec):
                    result = evaluate(f"git {subcommand} -- {spec}")
                    self.assertEqual(decision(result), "deny")
                    self.assertEqual(rule(result), f"tree-wide git {subcommand} pathspec reverts everyone's uncommitted work.")
        self.assertEqual(decision(evaluate("git checkout HEAD -- packages/aegis .")), "deny")
        self.assertEqual(decision(evaluate("git restore --staged -- .")), "deny")

    def test_denies_absolute_pathspec_equal_to_cwd(self):
        self.assertEqual(decision(evaluate(f"git checkout -- {MONOREPO}")), "deny")
        self.assertEqual(decision(evaluate(f"git restore -- {MONOREPO}/")), "deny")

    def test_denies_absolute_pathspec_equal_to_repo_root(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as root:
            os.makedirs(os.path.join(root, ".git"))
            cwd = os.path.join(root, "packages", "aegis")
            os.makedirs(cwd)
            self.assertEqual(decision(evaluate(f"git checkout -- {root}", cwd=cwd)), "deny")
            self.assertEqual(decision(evaluate(f"git restore --staged -- {root}/", cwd=cwd)), "deny")
            self.assertEqual(decision(evaluate(f"git checkout -- {cwd}", cwd=cwd)), "deny")
            self.assertIsNone(evaluate(f"git checkout -- {cwd}/src", cwd=cwd))
            self.assertIsNone(evaluate(f"git restore -- {root}/packages/other", cwd=cwd))

    def test_positive_pathspec_magic_is_decided_by_the_path_after_it(self):
        for spec in ("':(glob)**'", "':(top)'", "':(top,glob)*'", "':(glob)*'", "':(glob)'"):
            for subcommand in ("checkout", "restore"):
                with self.subTest(subcommand=subcommand, spec=spec):
                    result = evaluate(f"git {subcommand} -- {spec}")
                    self.assertEqual(decision(result), "deny")
                    self.assertEqual(rule(result), f"tree-wide git {subcommand} pathspec reverts everyone's uncommitted work.")
        self.assertIsNone(evaluate("git restore -- ':(glob)src/**/*.ts'"))
        self.assertIsNone(evaluate("git checkout -- ':(top)packages/aegis'"))
        self.assertIsNone(evaluate("git checkout -- ':(top,glob)*.ts'"))

    def test_denies_exclude_only_pathspecs_as_tree_wide(self):
        for command in (
            "git checkout -- ':!src'",
            "git restore -- ':(exclude)src'",
            "git checkout -- ':^src'",
            "git restore --staged -- ':!src'",
            "git checkout -- ':(top,exclude)src'",
            "git restore -- ':!src' ':^docs'",
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), f"tree-wide git {command.split()[1]} pathspec reverts everyone's uncommitted work.")
        self.assertIsNone(evaluate("git restore -- src ':!src/gen'"))
        self.assertIsNone(evaluate("git checkout -- ':(top)src' ':(exclude)src/gen'"))

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

    def test_permits_scoped_relative_pathspecs(self):
        self.assertIsNone(evaluate("git checkout -- ./packages/aegis"))
        self.assertIsNone(evaluate("git restore -- ../packages/aegis"))
        self.assertIsNone(evaluate("git restore -- $PWD/src"))
        self.assertIsNone(evaluate("git restore -- ${PWD}/src"))

    def test_denies_tree_wide_restore(self):
        self.assertEqual(decision(evaluate("git restore .")), "deny")
        self.assertEqual(decision(evaluate("git restore --staged .")), "deny")

    def test_permits_pathspec_scoped_restore(self):
        self.assertIsNone(evaluate("git restore -- packages/aegis/src/a.ts"))
        self.assertIsNone(evaluate("git restore --staged -- packages/aegis/src/a.ts"))
        self.assertIsNone(evaluate("git restore --staged -- src/"))
        self.assertIsNone(evaluate("git restore --staged -- file"))

    def test_denies_switch_discard_or_force(self):
        self.assertEqual(decision(evaluate("git switch --discard-changes main")), "deny")
        self.assertEqual(decision(evaluate("git switch -f main")), "deny")

    def test_permits_plain_switch_and_create(self):
        self.assertIsNone(evaluate("git switch main"))
        self.assertIsNone(evaluate("git switch -c feat/x"))
        self.assertIsNone(evaluate("git switch -cfeat/x"))


class GitPushTests(unittest.TestCase):
    def test_permits_push_the_permission_layer_asks(self):
        for command in ("git push", "git push --force-with-lease origin HEAD", "git push origin main"):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_permits_fetch_pull_log_diff(self):
        self.assertIsNone(evaluate("git fetch origin"))
        self.assertIsNone(evaluate("git pull --rebase"))
        self.assertIsNone(evaluate("git log --stat"))
        self.assertIsNone(evaluate("git diff HEAD~1 -- file"))


class GitAliasTests(unittest.TestCase):
    def test_denies_alias_defined_by_global_option(self):
        self.assertEqual(decision(evaluate("git -c alias.s=stash s")), "deny")
        self.assertEqual(decision(evaluate("git -c alias.x='!rm -rf .' x")), "deny")
        self.assertEqual(decision(evaluate("git -calias.s=stash s")), "deny")

    def test_alias_key_is_matched_case_insensitively(self):
        for command in ("git -c ALIAS.s=stash s", "git -c Alias.s=stash s", "git -cALIAS.s=stash s"):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")

    def test_permits_other_global_config(self):
        self.assertIsNone(evaluate("git -c core.pager=cat log --stat"))
        self.assertIsNone(evaluate("git -c core.pager=cat log -1"))
        self.assertIsNone(evaluate("git --no-pager log -1"))
        self.assertIsNone(evaluate("git -C packages/aegis log -1"))


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
        self.assertIsNone(evaluate('git commit -m "feat(aegis): add thing" -- packages/aegis'))
        self.assertIsNone(evaluate('git commit -m "fix: x" -- packages/aegis'))
        self.assertIsNone(evaluate('git commit -m "docs: RFC 6749 §3.1.1" -- a'))

    def test_message_attached_to_short_flag_is_not_read_as_flags(self):
        self.assertIsNone(evaluate('git commit -m"feat: add thing" -- packages/aegis'))
        self.assertIsNone(evaluate('git commit -qm "feat: add thing" -- packages/aegis'))
        self.assertEqual(rule(evaluate("git commit -ma -- packages/aegis")), SUBJECT_RULE)
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

    def test_denies_message_from_another_commit_or_template(self):
        for command, flag in (
            ("git commit -C HEAD -- a", "-C"),
            ("git commit -c HEAD~1 -- a", "-c"),
            ("git commit --reuse-message=HEAD -- a", "--reuse-message"),
            ("git commit --reedit-message HEAD -- a", "--reedit-message"),
            ("git commit -t tpl.txt -- a", "-t"),
            ("git commit --template=tpl.txt -- a", "--template"),
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), f"git commit {flag} takes the message from outside the command.")

    def test_denies_shell_expanded_message(self):
        for command, flag in (
            ('git commit -m "fix: $MSG" -- a', "-m"),
            ('git commit -m "fix: ${MSG}" -- a', "-m"),
            ('git commit -m "fix: `date`" -- a', "-m"),
            ('git commit -m "fix: $(cat msg)" -- a', "-m"),
            ('git commit --message="fix: $MSG" -- a', "--message"),
            ('git commit --message "fix: $MSG" -- a', "--message"),
            ('git commit -qm "fix: $MSG" -- a', "-m"),
            ('git commit -m"fix: $MSG" -- a', "-m"),
            ('git commit -m "fix: cost is $5" -- a', "-m"),
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), f"git commit {flag} takes the message from outside the command.")

    def test_message_source_is_denied_before_the_attribution_scan(self):
        result = evaluate('git commit -F msg.txt -m "Co-Authored-By: x" -- a')
        self.assertEqual(rule(result), "git commit -F takes the message from outside the command.")

    def test_permits_literal_message(self):
        self.assertIsNone(evaluate('git commit -m "fix: x" -- a'))
        self.assertIsNone(evaluate("git commit -m 'fix: x' -m 'body' -- a"))
        self.assertIsNone(evaluate('git commit --message="fix: x" -- a'))

    def test_permits_stdin_message_from_a_heredoc(self):
        self.assertIsNone(evaluate("git commit -F - -- packages/aegis <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit --file=- -- packages/aegis <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit -F- -- packages/aegis <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<'EOF'\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a << EOF\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<EOF\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<-EOF\nfix: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a << 'EOF'\nfix: x\nEOF"))
        self.assertIsNone(evaluate('git commit -F - -- a <<"EOF"\nfix: x\nEOF'))
        self.assertIsNone(evaluate("git commit -F - -- a <<EOF # note\nfeat: x\nEOF"))

    def test_denies_stdin_message_without_a_heredoc(self):
        for command in (
            "printf 'feat: x' | git commit -F - -- a",
            "cat msg.txt | git commit --file=- -- a",
            "git commit -F - -- a",
            "git commit --file=- -- a",
            "git commit -F- -- a",
            "git commit -qF - -- a",
            'git commit -F - -- a <<< "Add thing"',
            'git commit -F - -- a <<< "feat: x"',
            "git commit -F - -- a <<",
            "cat msg.txt | git commit -F - --trailer '<<EOF' -- a",
            "git commit -F - -- a '<<EOF'",
            "git commit -F - -- a \\<<EOF",
            "git commit -F - -- a # <<EOF\nfeat: x\nEOF",
            "cat msg.txt | git commit -F - -- a # <<'EOF'\nfeat: x\nEOF",
            "git commit -F - -- a $(cat <<EOF )\nfeat: x\nEOF",
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), "git commit -F - takes the message from a pipe or stdin the guard cannot read.")
        command = "printf 'Co-Authored-By: x' | git commit -F - -- a"
        result = evaluate(command)
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), f"commit text contains '{command}'; commit messages carry no Claude attribution.")

    def test_pathspec_after_double_dash_is_not_a_message_source(self):
        self.assertIsNone(evaluate('git commit -m "fix: x" -- -C'))
        self.assertIsNone(evaluate("git commit -F - -- '$dir' <<'EOF'\nfix: x\nEOF"))


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
                self.assertEqual(decision(evaluate(f'git commit -m "fix: thing\n\n{line}" -- packages/aegis')), "deny")

    def test_denies_trailer_keys_case_insensitively_and_indented(self):
        for line in ("co-authored-by: X", "CO-AUTHORED-BY: X", "claude-session: url", "  co-authored-by: x"):
            with self.subTest(line=line):
                self.assertEqual(decision(evaluate(f'git commit -m "fix: thing\n\n{line}" -- packages/aegis')), "deny")

    def test_deny_reason_names_the_offending_line(self):
        result = evaluate('git commit -m "fix: thing\n\n  co-authored-by: x" -- packages/aegis')
        self.assertIn("'co-authored-by: x'", reason(result))

    def test_product_names_are_not_attribution(self):
        self.assertIsNone(evaluate('git commit -m "feat: source-of-truth repo for Claude Code configuration" -- a'))
        self.assertIsNone(evaluate('git commit -m "fix: thing\n\nAnthropic docs describe this" -- a'))
        self.assertIsNone(evaluate('git commit -m "docs: mention claude code and anthropic" -- a'))

    def test_denies_trailer_key_anywhere_in_a_line(self):
        result = evaluate('git commit -m "fix: thing\n\nthe hook denies Co-Authored-By: trailers" -- a')
        self.assertEqual(decision(result), "deny")
        self.assertEqual(rule(result), "commit text contains 'the hook denies Co-Authored-By: trailers'; commit messages carry no Claude attribution.")
        self.assertEqual(decision(evaluate('git commit -m "fix: thing\n\nsee claude-session: url" -- a')), "deny")

    def test_attribution_phrase_is_the_claude_code_link(self):
        self.assertIsNone(evaluate("git commit -m 'fix: generated with care' -- a"))
        self.assertIsNone(evaluate("git commit -m 'feat: add robot 🤖 emoji' -- a"))
        result = evaluate('git commit -m "fix: thing\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)" -- a')
        self.assertEqual(decision(result), "deny")
        self.assertEqual(
            rule(result),
            "commit text contains '🤖 Generated with [Claude Code](https://claude.com/claude-code)'; commit messages carry no Claude attribution.",
        )

    def test_denies_single_line_message_that_is_a_trailer(self):
        self.assertEqual(rule(evaluate('git commit -m "Co-Authored-By: x" -- a')), SUBJECT_RULE)
        self.assertEqual(
            rule(evaluate('git commit -m "fix: Co-Authored-By: x" -- a')),
            "commit text contains 'fix: Co-Authored-By: x'; commit messages carry no Claude attribution.",
        )

    def test_denies_marker_in_heredoc_body(self):
        command = "git commit -F - -- packages/aegis <<'EOF'\nfix: thing\n\nCo-Authored-By: Someone\nEOF"
        self.assertEqual(decision(evaluate(command)), "deny")

    def test_permits_clean_message_with_lowercase_claude_path(self):
        self.assertIsNone(evaluate('git commit -m "chore: hooks" -- .claude/hooks/x.py'))
        self.assertIsNone(evaluate('git commit -m "chore: hooks" -- .claude/hooks/git-guard.py'))

    def test_marker_outside_a_commit_is_ignored(self):
        self.assertIsNone(evaluate('grep -rn "Co-Authored-By" .'))


class GitCommitSubjectTests(unittest.TestCase):
    def test_denies_non_conventional_subject(self):
        for command in (
            'git commit -m "add thing" -- a',
            'git commit -m "Fixed the thing" -- a',
            'git commit -m "Feat: x" -- a',
            'git commit -m "feat:x" -- a',
            'git commit -m "feat(Aegis): x" -- a',
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
            'git commit -m "feat(aegis): add thing" -- a',
            'git commit -m "fix: x" -- a',
            'git commit -m "docs: RFC 6749 §3.1.1" -- a',
            'git commit -m "chore(repo): drop dependabot" -- a',
            'git commit -m "refactor(proteus,iris): share the compiler" -- a',
            'git commit -m "revert: feat(x): y" -- a',
            'git commit -m "build(deps): bump cbor2" -- a',
            'git commit -m "test(pylon-http): cover 409" -- a',
            'git commit --message="ci: split lanes" -- a',
            'git commit -qm "perf: x" -- a',
            'git commit -m "fix(aegis): x" -m "Body prose that need not be conventional." -- a',
            "git commit -F - -- a <<'EOF'\nfeat: add thing\nEOF",
            "git commit -F - -- a <<'EOF'\nfix(aegis): x\n\nbody\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_subject_is_the_first_non_empty_line_of_the_readable_message(self):
        self.assertIsNone(evaluate("git commit -F - -- a <<'EOF'\n\nstyle: x\nEOF"))
        self.assertIsNone(evaluate('git commit -m "\nfix: x\n\nBody line" -- a'))
        self.assertEqual(rule(evaluate("git commit -F - -- a <<'EOF'\n\nAdd thing\n\nfix: x\nEOF")), SUBJECT_RULE)

    def test_heredoc_body_is_the_one_opened_by_the_commit(self):
        for command in (
            "cat > x <<'EOF'\nAdd thing\nEOF\ngit commit -F - -- x <<'EOF'\nfeat: x\nEOF",
            "git commit -F - -- x <<'EOF'\nfeat: x\nEOF\ncat > x <<'EOF'\nAdd thing\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))
        for command in (
            "git commit -F - -- x <<'EOF'\nAdd thing\nEOF\ncat > x <<'EOF'\nfeat: x\nEOF",
            "cat > x <<'EOF'\nfeat: x\nEOF\ngit commit -F - -- x <<'EOF'\nAdd thing\nEOF",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), SUBJECT_RULE)

    def test_each_commit_reads_its_own_heredoc_including_nested_commits(self):
        for command, expected in (
            ("git commit -F - -- a <<'EOF'\nfeat: x\nEOF\ngit commit -F - -- a <<'EOF'\nAdd thing\nEOF", SUBJECT_RULE),
            ("sh -c \"git commit -F - -- a <<'EOF'\nAdd thing\nEOF\"", SUBJECT_RULE),
            ("bash -c \"git commit -F - -- a <<'EOF'\nAdd thing\nEOF\"", SUBJECT_RULE),
            ("eval \"git commit -F - -- a <<'EOF'\nAdd thing\nEOF\"", SUBJECT_RULE),
            ("echo $(git commit -F - -- a <<'EOF'\nfix: x\n\nsee §3\nEOF\n)", SECTION_RULE),
            ("echo `git commit -F - -- a <<'EOF'\nfix: x\n\nsee §3\nEOF\n`", SECTION_RULE),
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), expected)
        for command in (
            "sh -c \"git commit -F - -- a <<'EOF'\nfeat: x\nEOF\"",
            "eval \"git commit -F - -- a <<'EOF'\nfeat: x\nEOF\"",
            "echo $(git commit -F - -- a <<'EOF'\nfeat: x\nEOF\n)",
            "echo `git commit -F - -- a <<'EOF'\nfeat: x\nEOF\n`",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_subject_rule_applies_only_to_message_text_the_guard_can_read(self):
        self.assertIsNone(evaluate("git commit -- a"))
        self.assertIsNone(evaluate("git commit --fixup=HEAD~1 -- a"))
        for command, source_rule in (
            ("git commit -F msg.txt -- a", "git commit -F takes the message from outside the command."),
            ("git commit -C HEAD -- a", "git commit -C takes the message from outside the command."),
            ('git commit -m "$MSG" -- a', "git commit -m takes the message from outside the command."),
            ("git commit -F - -- a", "git commit -F - takes the message from a pipe or stdin the guard cannot read."),
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), source_rule)

    def test_flag_and_pathspec_rules_come_before_the_subject_rule(self):
        self.assertEqual(rule(evaluate('git commit -a -m "add thing"')), "git commit -a/--all/--no-verify commits the whole tree or skips hooks.")
        self.assertEqual(rule(evaluate('git commit -m "add thing"')), "git commit without a pathspec commits the whole index.")

    def test_subject_text_outside_a_commit_is_not_judged(self):
        self.assertIsNone(evaluate('echo "Fixed the thing"'))
        self.assertIsNone(evaluate('git log --grep "Fixed"'))


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
                self.assertIsNone(evaluate(f'git commit -m "fix(aegis): align with {text}" -- a'))
        self.assertIsNone(evaluate('git commit -m "docs: OIDC Core §3.1.2.1" -- a'))
        self.assertIsNone(evaluate("git commit -F - -- a <<'EOF'\nfix: x\n\nRFC 6749 §3.1.1\nEOF"))

    def test_section_sign_outside_the_readable_message_is_not_judged(self):
        self.assertIsNone(evaluate('git commit -m "docs: x" -- "docs/§3.md"'))
        self.assertIsNone(evaluate('echo "§3" && git commit -m "fix: x" -- a'))
        self.assertIsNone(evaluate('grep -rn "§3" docs'))

    def test_subject_rule_comes_before_the_section_rule(self):
        self.assertEqual(rule(evaluate('git commit -m "Add §3" -- a')), SUBJECT_RULE)


class VerifyPipeTests(unittest.TestCase):
    def test_denies_verify_run_piped_to_a_pager(self):
        for command in (
            "npm test | tail -50",
            "npm t | tail",
            "npm test -- Aegis 2>&1 | tail -5",
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
            "bash /Users/jonn/Projects/ai-config/tests/test_apply.sh | head",
        ):
            with self.subTest(command=command):
                result = evaluate(command)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), PAGER_RULE)
                self.assertEqual(permitted(result), PAGER_PERMITTED)

    def test_npm_options_before_the_subcommand_are_skipped(self):
        for command in (
            "npm --silent test | tail",
            "npm -s test | tail",
            "npm --loglevel silent test | tail",
            "npm --loglevel=silent test | tail",
            "npm --prefix packages/aegis test | tail",
            "npm -w packages/aegis test | tail",
            "npm --workspace packages/aegis run test:unit | tail",
            "npm run --silent test | head",
            "npm -s run --if-present build | tail",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), PAGER_RULE)

    def test_pipes_inside_a_substitution_or_shell_string_are_judged(self):
        for command in ("echo $(npm test | tail)", 'sh -c "npm test | tail"', 'eval "npm test | head"'):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), PAGER_RULE)

    def test_last_command_of_a_subshell_joins_the_outer_pipeline(self):
        for command in ("(cd packages/aegis && npm test) | tail -5", "(npm test | tail)", "cd packages/aegis && npm test | tail -3"):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), PAGER_RULE)

    def test_earlier_commands_of_a_subshell_do_not_join_the_outer_pipeline(self):
        self.assertIsNone(evaluate("(npm test; echo done) | tail"))

    def test_permits_redirect_and_pager_in_a_separate_list(self):
        for command in (
            'npm test > "$TMPDIR/out.txt" 2>&1',
            'npm test > "$TMPDIR/o.txt" 2>&1; tail -50 "$TMPDIR/o.txt"',
            "npm test && tail out.txt",
            "npm test || tail out.txt",
            "npm test & tail out.txt",
            "npm test &> out.txt",
            "tail -5 cases.txt | npm test",
            "pytest > out.txt 2>&1\ntail -20 out.txt",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_permits_non_verify_pipes(self):
        for command in (
            "ls | tail",
            "git log | head",
            "git diff --stat | head -20",
            "npm ls | head",
            "npm --prefix packages/aegis ls | head",
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

    def test_npm_npx_and_node_invocations_without_a_pipe_are_silent(self):
        for command in ("npx tsx script.ts", "npm exec -- tsc", "npm --version", "node scripts/build.js"):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_redirection_ampersands_do_not_split_a_pipeline(self):
        self.assertEqual(rule(evaluate("npm test 2>&1 | tail")), PAGER_RULE)
        self.assertEqual(rule(evaluate("npm test >out.txt 2>&1 | head")), PAGER_RULE)
        self.assertEqual(decision(evaluate("true & git stash")), "deny")
        self.assertEqual(rule(evaluate("true &> out.txt & git stash")), "git stash silently destroys uncommitted work in a shared tree.")
        self.assertIsNone(evaluate("npm test &> out.txt & tail out.txt"))
        self.assertEqual(rule(evaluate("npm test &> out.txt | tail")), PAGER_RULE)


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

    def test_wrapper_options_are_skipped_before_the_program(self):
        for command in (
            "xargs -n1 git stash",
            "xargs -n 1 -P 4 git stash",
            "xargs -0 -r -I {} git stash",
            "xargs -a list.txt git stash",
            "exec -a name git stash",
            "command -p git stash",
            "sudo -u root git stash",
            "sudo -E -n git stash",
            "sudo -- git stash",
            "doas -u root git stash",
            "env -i git stash",
            "env -u X git stash",
            "env -i GIT_DIR=.git git stash",
            "nice -n 5 git stash",
            "caffeinate -i -t 60 git stash",
            "timeout -s KILL 10 git stash",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")

    def test_wrappers_by_absolute_path_are_stripped(self):
        for command, expected in (
            ("/usr/bin/sudo git stash", "git stash silently destroys uncommitted work in a shared tree."),
            ("/usr/bin/env -i git stash", "git stash silently destroys uncommitted work in a shared tree."),
            ("/usr/bin/timeout 5 git clean -fdx", CLEAN_RULE),
            ("/usr/bin/xargs rm -rf", SUBSTITUTION_RULE),
            ("/usr/bin/sudo -u root /usr/bin/xargs -0 rm -f", SUBSTITUTION_RULE),
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), expected)

    def test_wrapped_harmless_programs_stay_silent(self):
        for command in ("xargs -n1 echo", "xargs -I {} echo {}", "env -i printenv", "nice -n 5 npm test", "exec ls", "sudo -u root ls"):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))


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

    def test_depth_limit_stops_recursion(self):
        self.assertEqual(decision(evaluate("echo $(echo $(echo $(git stash)))")), "deny")
        self.assertIsNone(evaluate("echo $(echo $(echo $(echo $(git stash))))"))
        self.assertIsNone(evaluate("echo $(echo $(echo $(echo $(echo $(git stash)))))"))
        self.assertEqual(rule(evaluate("echo $(echo $(echo $(npm test | tail)))")), PAGER_RULE)
        self.assertIsNone(evaluate("echo $(echo $(echo $(echo $(npm test | tail))))"))

    def test_permits_safe_indirection(self):
        self.assertIsNone(evaluate('sh -c "git status"'))
        self.assertIsNone(evaluate("echo $(git rev-parse HEAD)"))
        self.assertIsNone(evaluate("eval ls"))


class ShellReadingTests(unittest.TestCase):
    def test_a_quoted_paren_does_not_close_a_substitution(self):
        self.assertIsNone(evaluate("git commit -F - -- a $(echo \")\") <<'EOF'\nfeat: x\nEOF"))
        self.assertEqual(rule(evaluate('echo $(git stash ")")')), STASH_RULE)
        self.assertEqual(rule(evaluate("echo \"$(git stash ')')\"")), STASH_RULE)
        self.assertEqual(rule(evaluate('echo $(echo ")"; git stash)')), STASH_RULE)

    def test_a_process_substitution_is_walked_and_is_one_span_to_the_outer_command(self):
        self.assertEqual(rule(evaluate("diff <(git stash) x")), STASH_RULE)
        self.assertEqual(rule(evaluate("tee >(git stash) < x")), STASH_RULE)
        self.assertEqual(rule(evaluate("git commit -F - -- a <(cat <<EOF)")), STDIN_RULE)
        self.assertIsNone(evaluate("git commit -F - -- a <(cat) <<EOF\nfeat: x\nEOF"))
        self.assertEqual(rule(evaluate("npm test <(true) | tail")), PAGER_RULE)

    def test_a_parameter_expansion_is_one_span_to_the_opener_test(self):
        for command in ("git commit -F - -- a ${X:-<<EOF}", "git commit -F - -- a ${X:- <<EOF }\nfeat: x\nEOF"):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), STDIN_RULE)
        self.assertIsNone(evaluate('git commit -F - -- a ${X:-"}"} <<EOF\nfeat: x\nEOF'))

    def test_ansi_c_quoting_is_a_quoted_span(self):
        self.assertEqual(rule(evaluate("git commit -F - -- a $'<<EOF'")), STDIN_RULE)
        self.assertIsNone(evaluate("git commit -F - -- a $'\\'' <<EOF\nfeat: x\nEOF"))
        self.assertIsNone(evaluate("git commit -m $'fix: x' -- a"))
        self.assertIsNone(evaluate("git commit -m $'\\x66ix: x' -- a"))
        self.assertEqual(rule(evaluate("git commit -m $'Add thing' -- a")), SUBJECT_RULE)
        self.assertEqual(rule(evaluate("git commit -m $'Add thing\\nfix: x' -- a")), SUBJECT_RULE)
        self.assertEqual(
            rule(evaluate("git commit -m $'fix: x\\n\\nCo-Authored-By: x' -- a")),
            "commit text contains 'Co-Authored-By: x'; commit messages carry no Claude attribution.",
        )

    def test_a_heredoc_opened_inside_a_substitution_belongs_to_the_inner_command(self):
        for command in ("git commit -F - -- a $(cat <<EOF)\nfeat: x\nEOF", "git commit -F - -- a `cat <<EOF`\nfeat: x\nEOF"):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), STDIN_RULE)
        self.assertEqual(rule(evaluate("echo $(git commit -F - -- a <<'EOF'\nAdd thing\nEOF\n)")), SUBJECT_RULE)
        self.assertEqual(rule(evaluate("echo `git commit -F - -- a <<'EOF'\nAdd thing\nEOF\n`")), SUBJECT_RULE)

    def test_a_comment_starts_after_whitespace_or_an_operator_and_hides_the_rest_of_its_line(self):
        for command in ("git commit -F - -- a ># <<EOF\nfeat: x\nEOF", "git commit -F - -- a >#<<EOF\nfeat: x\nEOF", "git commit -F - -- a;#<<EOF\nfeat: x\nEOF"):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), STDIN_RULE)
        self.assertIsNone(evaluate("echo x # ; git stash"))
        self.assertIsNone(evaluate("echo x;# git stash"))
        self.assertEqual(rule(evaluate("echo x # ; git stash\ngit clean -fdx")), CLEAN_RULE)

    def test_a_hash_after_an_escaped_space_or_a_continued_word_continues_the_word(self):
        self.assertEqual(rule(evaluate("echo \\ #; git stash")), STASH_RULE)
        self.assertEqual(rule(evaluate("echo a\\\n#; git stash")), STASH_RULE)
        self.assertIsNone(evaluate("echo a \\\n#; git stash"))

    def test_a_process_substitution_inside_an_unquoted_expansion_is_walked(self):
        self.assertEqual(rule(evaluate("echo ${X:-<(git stash)}")), STASH_RULE)
        self.assertIsNone(evaluate('echo "${X:-<(git stash)}"'))
        self.assertEqual(rule(evaluate('echo "${X:-$(git stash)}"')), STASH_RULE)

    def test_a_single_quoted_substitution_is_literal(self):
        self.assertIsNone(evaluate("echo '$(git stash)'"))
        self.assertEqual(rule(evaluate("rm -rf '$(git stash)'")), SUBSTITUTION_RULE)

    def test_a_line_continuation_is_removed(self):
        self.assertEqual(rule(evaluate("git \\\nstash")), STASH_RULE)
        self.assertEqual(rule(evaluate("git \\\nclean -fdx")), CLEAN_RULE)
        self.assertEqual(rule(evaluate("git \\\ncommit -m 'Add thing' -- a")), SUBJECT_RULE)
        self.assertIsNone(evaluate("git commit -F - -- a \\\n<<'EOF'\nfeat: x\nEOF"))
        self.assertIsNone(evaluate('git commit -m "fix: x" \\\n-- a'))

    def test_escaped_backticks_nest_a_substitution(self):
        self.assertEqual(rule(evaluate("echo `echo \\`git stash\\``")), STASH_RULE)

    def test_a_hash_inside_a_word_escaped_or_quoted_stays_a_word(self):
        for command in (
            "git commit -F - -- a#b <<EOF\nfeat: x\nEOF",
            "git commit -F - -- a \\# <<EOF\nfeat: x\nEOF",
            "git commit -F - -- a '#' <<EOF\nfeat: x\nEOF",
            "git commit -F - -- a >x#<<EOF\nfeat: x\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))
        for command in ("echo a#b; git stash", "echo \\#; git stash", "echo '#'; git stash"):
            with self.subTest(command=command):
                self.assertEqual(rule(evaluate(command)), STASH_RULE)

    def test_a_heredoc_operator_needs_no_space_before_it(self):
        self.assertIsNone(evaluate("git commit -F - -- a<<EOF\nfeat: x\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a<<'EOF'\nfeat: x\nEOF"))
        self.assertEqual(rule(evaluate("git commit -F - -- a<<'EOF'\nAdd thing\nEOF")), SUBJECT_RULE)
        self.assertEqual(rule(evaluate("cat msg.txt | git commit -F - --trailer '<<EOF' -- a")), STDIN_RULE)

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
        os.makedirs(os.path.join(cls.root, "packages", "aegis", "dist"))
        os.symlink("src", os.path.join(cls.root, "link"))
        os.symlink(os.path.join("..", "..", "..", "src"), os.path.join(cls.root, "packages", "aegis", "dist", "link"))
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
            "rm -rf packages/aegis/dist",
            "rm -rf packages/aegis/dist/bundle.js",
            "rm -rf node_modules dist",
            f"rm -rf {self.root}/node_modules",
            "sudo rm -rf node_modules",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

    def test_absent_path_is_judged_by_check_ignore_without_a_trailing_slash(self):
        for command in ("rm -rf coverage", "rm -R __pycache__", "rm -rf nonexistent"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("rm -rf dist/new"))
        self.assertIsNone(self.in_repo("rm nonexistent.pyc"))

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
        self.assertIsNone(self.in_repo("rm -rf dist", "packages/aegis"))
        self.assertIsNone(self.in_repo("rm -rf ../../node_modules", "packages/aegis"))
        self.assertEqual(rule(self.in_repo("rm -rf .", "packages/aegis")), RM_RULE)
        self.assertEqual(rule(self.in_repo("rm -rf ../../src", "packages/aegis")), RM_RULE)

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
        for command in ("rm -rf link/", "rm -rf link", "rm -rf ./link/", f"rm -rf {self.root}/link/", "rm -rf packages/aegis/dist/link/"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)

    def test_denies_recursive_rm_of_the_repository_root(self):
        for command, path in (
            ("rm -rf .", ""),
            ("rm -rf ./", ""),
            (f"rm -rf {self.root}", ""),
            (f"rm -rf {self.root}/", ""),
            ("rm -rf ../..", "packages/aegis"),
            (f"rm -rf {self.root}", "packages/aegis"),
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

    def test_first_deny_in_segment_order_wins(self):
        self.assertEqual(rule(self.in_repo("rm -rf src; git stash")), RM_RULE)
        self.assertEqual(rule(self.in_repo("git stash; rm -rf src")), STASH_RULE)

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

    def test_permits_literal_tmpdir_when_unset_in_environment(self):
        with mock.patch.dict(os.environ, {"TMPDIR": ""}):
            self.assertIsNone(self.in_repo('rm -rf "$TMPDIR/x"'))
            self.assertEqual(rule(self.in_repo("rm -rf $TMPDIR/../x")), RM_RULE)

    def test_permits_resolved_tmpdir_value(self):
        self.assertIsNone(self.in_repo(f"rm -rf {TMPDIR}/out"))
        self.assertIsNone(self.in_repo(f"rm -rf {TMPDIR}"))

    def test_denies_plain_rm_of_a_path_git_does_not_ignore(self):
        for command in ("rm -f packages/aegis/src/x.ts", "rm src/a.ts", "rm notes.txt", "rm -- src/a.ts", "rm node_modules src/a.ts", "rm dist/out.js notes.txt"):
            with self.subTest(command=command):
                result = self.in_repo(command)
                self.assertEqual(rule(result), RM_RULE)
                self.assertTrue(permitted(result).startswith("mv "))

    def test_permits_plain_rm_of_a_git_ignored_or_temp_path(self):
        for command in ("rm -f dist/out.js", "rm dist/out.js", 'rm "$TMPDIR/x"', "rm -- packages/aegis/dist/bundle.js", "rm -f dist/out.js packages/aegis/dist/bundle.js"):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

    def test_permits_rm_with_no_target(self):
        self.assertIsNone(self.in_repo("rm"))
        self.assertIsNone(self.in_repo("rm -f"))

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

    def test_check_ignore_runs_once_from_the_repository_root(self):
        with mock.patch.object(git_guard.subprocess, "run", return_value=mock.Mock(returncode=1, stdout=b"")) as run:
            self.assertEqual(rule(self.in_repo("rm -rf dist", "packages/aegis")), RM_RULE)
        self.assertEqual([call.args[0] for call in run.call_args_list], [["git", "-C", self.root, "check-ignore", "-v", "-z", "--stdin", "--"]])
        self.assertEqual([call.kwargs["input"] for call in run.call_args_list], [b"packages/aegis/dist\0"])
        self.assertEqual({call.kwargs["timeout"] for call in run.call_args_list}, {2})

    def test_one_check_ignore_call_judges_every_target_of_a_segment(self):
        targets = "node_modules dist packages/aegis/dist dist/out.js node_modules/pkg foo.log"
        with mock.patch.object(git_guard.subprocess, "run", wraps=subprocess.run) as run:
            self.assertIsNone(self.in_repo(f"rm -rf {targets}"))
        self.assertEqual([call.kwargs["input"] for call in run.call_args_list], [b"node_modules\0dist\0packages/aegis/dist\0dist/out.js\0node_modules/pkg\0foo.log\0"])
        with mock.patch.object(git_guard.subprocess, "run", wraps=subprocess.run) as run:
            result = self.in_repo(f"rm -rf {targets} src")
        self.assertEqual(rule(result), RM_RULE)
        self.assertTrue(permitted(result).startswith("mv "))
        self.assertEqual(run.call_count, 1)

    def test_each_segment_gets_its_own_call_inside_the_budget(self):
        with mock.patch.object(git_guard.subprocess, "run", wraps=subprocess.run) as run:
            self.assertIsNone(self.in_repo("rm -rf node_modules && rm -rf dist && rm -f dist/out.js && rm -rf packages/aegis/dist && rm foo.log"))
        self.assertEqual([call.kwargs["input"] for call in run.call_args_list], [b"node_modules\0", b"dist\0", b"dist/out.js\0", b"packages/aegis/dist\0", b"foo.log\0"])
        self.assertEqual({call.kwargs["timeout"] for call in run.call_args_list}, {2})

    def test_a_non_ascii_ignored_target_passes(self):
        for command in ("rm résumé.log", "rm -rf résumé.log", "rm 'résumé.pyc'"):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))
        self.assertEqual(rule(self.in_repo("rm résumé.txt")), RM_RULE)

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

    def test_targets_are_read_the_way_the_shell_reads_them(self):
        self.assertEqual(rule(self.in_repo("rm -rf $'src'")), RM_RULE)
        self.assertIsNone(self.in_repo("rm -rf $'dist'"))
        self.assertEqual(rule(self.in_repo('rm -rf $(echo ")")/src')), SUBSTITUTION_RULE)
        self.assertEqual(rule(self.in_repo("rm -rf ${X:-src}")), SUBSTITUTION_RULE)
        self.assertEqual(rule(self.in_repo("cat <(rm -rf src)")), RM_RULE)
        self.assertIsNone(self.in_repo("rm -rf dist # src"))
        self.assertEqual(rule(self.in_repo("rm -rf dist \\#")), RM_RULE)

    def test_an_ansi_c_body_decodes_before_it_becomes_a_target(self):
        for command in ("rm -rf $'src\\x00.log'", "rm -rf $'src\\0.log'", "rm -rf $'\\x24TMPDIR/x'", "rm -rf $'\\u0064ist'"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("rm -rf $'dist\\x00/src'"))
        self.assertIsNone(self.in_repo("rm -rf $'\\x64ist'"))

    def test_an_escaped_dollar_names_a_literal_path_not_the_temp_variable(self):
        for command in ("rm -rf \\$TMPDIR/x", 'rm -rf "\\$TMPDIR/x"'):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("rm -rf $TMPDIR/x"))


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
            ("find . -name '*.pyc' -delete", "packages/aegis"),
            ("find ../.. -name '*.pyc' -delete", "packages/aegis"),
        ):
            with self.subTest(command=command, path=path):
                self.assertIsNone(self.in_repo(command, path))

    def test_permits_any_expression_from_a_safe_or_ignored_start_path(self):
        for command in (
            "find node_modules -delete",
            "find node_modules ! -name x -o -newer y -ok rm {} \\;",
            'find node_modules -name "$PAT" -delete',
            "find dist -name '*.js' -delete",
            "find packages/aegis/dist -type f -exec rm -rf {} +",
            'find "$TMPDIR/x" -newer y -delete',
            "find $TMPDIR/x -name '*.log' -delete",
            'find "${TMPDIR}/x" -type d -exec rm -rf {} +',
            "find /tmp/claude/x -delete",
            "find -P node_modules -delete",
            "find -f /tmp/claude/x -delete",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))

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

    def test_prompting_actions_delete_and_are_never_the_shape(self):
        for command in (
            "find . -name '*.pyc' -ok rm {} \\;",
            "find . -name '*.pyc' -okdir rm {} \\;",
            "find . -name '*.pyc' -ok sh -c 'rm -rf dist' \\;",
            "find . -type d -name __pycache__ -okdir rm -rf {} \\;",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -ok cat {} \\;"))

    def test_name_retry_with_a_slash_applies_only_with_type_d(self):
        for command in (
            "find . -name build -delete",
            "find . -type f -name build -delete",
            "find . -name __pycache__ -delete",
            "find . -path '*/node_modules' -prune -exec rm -rf {} +",
            "find . -name '*.pyc' -name __pycache__ -delete",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("find . -type d -name __pycache__ -delete"))

    def test_names_and_their_slash_forms_share_one_call(self):
        with mock.patch.object(git_guard.subprocess, "run", return_value=mock.Mock(returncode=1, stdout=b"")) as run:
            self.assertEqual(rule(self.in_repo("find packages -type d -name __pycache__ -name cache -delete")), RM_RULE)
        self.assertEqual([call.args[0][3:] for call in run.call_args_list], [["check-ignore", "-v", "-z", "--stdin", "--"]] * 2)
        self.assertEqual({os.path.normpath(call.args[0][2]) for call in run.call_args_list}, {self.root})
        self.assertEqual([call.kwargs["input"] for call in run.call_args_list], [b"packages\0", b"__pycache__\0cache\0__pycache__/\0cache/\0"])
        with mock.patch.object(git_guard.subprocess, "run", return_value=mock.Mock(returncode=1, stdout=b"")) as run:
            self.assertEqual(rule(self.in_repo("find . -name '*.pyc' -delete")), RM_RULE)
        self.assertEqual([call.kwargs["input"] for call in run.call_args_list], [b"*.pyc\0"])

    def test_an_anchored_pattern_does_not_exempt_a_name_that_matches_every_directory(self):
        for command in (
            "find . -type d -name build -exec rm -rf {} +",
            "find packages -type d -name build -exec rm -rf {} +",
            "find . -type d -name build -delete",
            "find . -name keep.log -delete",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("find packages -type d -name dist -exec rm -rf {} +"))
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -delete"))
        self.assertIsNone(self.in_repo("find . -name x.log -delete"))
        self.assertIsNone(self.in_repo("find . -type d -name cache -delete"))
        self.assertIsNone(self.in_repo("find . -type d -name staging -delete"))
        self.assertIsNone(self.in_repo("find . -type d -name twice -delete"))
        self.assertIsNone(self.in_repo("find . -path '*/dist/*' -delete"))

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

    def test_names_are_judged_from_the_repository_root(self):
        for command in ("find ../.. -name '*.ts' -delete", "find ../.. -name a.ts -exec rm -rf {} +", "find ../.. -type d -name src -delete"):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command, "node_modules/pkg")), RM_RULE)
        self.assertIsNone(self.in_repo("find ../.. -name '*.pyc' -delete", "node_modules/pkg"))
        self.assertIsNone(self.in_repo("find ../.. -type d -name __pycache__ -delete", "node_modules/pkg"))
        self.assertIsNone(self.in_repo("find . -name '*.ts' -delete", "node_modules/pkg"))

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

    def test_a_start_path_in_the_shape_is_judged_by_its_real_path(self):
        for command in (
            "find escape -name '*.pyc' -delete",
            "find escape/other -name '*.pyc' -delete",
            "find . escape -name '*.pyc' -delete",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertIsNone(self.in_repo("find link -type d -name __pycache__ -exec rm -rf {} +"))
        self.assertIsNone(self.in_repo("find link/x -name '*.pyc' -delete"))
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -delete"))

    def test_git_commit_inside_an_action_cannot_be_judged(self):
        result = self.in_repo("find . -exec git commit -m 'x' -- src/a.ts \\;")
        self.assertEqual(rule(result), "git commit inside a find action cannot be judged.")
        self.assertEqual(permitted(result), "run git commit as its own command with -- <paths>.")
        self.assertEqual(rule(self.in_repo("find . -exec sh -c 'git commit -m \"fix: x\" -- src/a.ts' \\;")), "git commit inside a find action cannot be judged.")
        self.assertEqual(rule(self.in_repo("find . -exec git commit -a -m 'x' \\;")), "git commit -a/--all/--no-verify commits the whole tree or skips hooks.")

    def test_an_unterminated_action_runs_to_the_end_of_the_command(self):
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -exec rm -rf {}"))
        self.assertEqual(rule(self.in_repo("find . -name '*.ts' -exec rm -rf {}")), RM_RULE)
        self.assertEqual(rule(self.in_repo("find . -name '*.pyc' -exec rm -rf {} src")), RM_RULE)

    def test_a_find_inside_an_action_is_judged_from_cwd_like_any_find(self):
        for command in (
            "find . -name '*.pyc' -exec find src -delete \\;",
            "find . -exec sh -c 'find src -delete' \\;",
            "find node_modules -exec find ../src -delete \\;",
            "find . -name '*.pyc' -exec sh -c 'find . -name \"*.ts\" -delete' \\;",
            "find node_modules -exec find {} -delete \\;",
            "find . -exec find . -exec find . -delete \\; \\;",
            "find . -name '*.pyc' -exec find . -name '*.pyc' -exec rm -rf src \\; \\;",
        ):
            with self.subTest(command=command):
                self.assertEqual(rule(self.in_repo(command)), RM_RULE)
        self.assertEqual(rule(self.in_repo("find . -exec find . -exec git stash \\; \\;")), "git stash silently destroys uncommitted work in a shared tree.")
        self.assertIsNone(self.in_repo("find . -name '*.pyc' -exec find {} -name '*.pyc' -delete \\;"))
        self.assertIsNone(self.in_repo("find node_modules -exec find node_modules -delete \\;"))
        self.assertIsNone(self.in_repo("find . -exec find . -name '*.ts' -exec cat {} + \\;"))

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

    def test_a_find_without_an_expression_or_with_an_empty_action_never_raises(self):
        for command in ("find", "find -L", "find -f", "find . -exec", "find . -exec find", "find . -exec find . -exec"):
            with self.subTest(command=command):
                self.assertIsNone(self.in_repo(command))
        self.assertEqual(rule(self.in_repo("find -f -delete -f")), RM_RULE)

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
        self.assertEqual(decision(evaluate("cd packages/aegis && npm test && git stash")), "deny")

    def test_denies_stash_after_semicolon_and_pipe(self):
        self.assertEqual(decision(evaluate("ls; git stash")), "deny")
        self.assertEqual(decision(evaluate("echo x | git stash")), "deny")
        self.assertEqual(decision(evaluate("true || git reset --hard")), "deny")
        self.assertEqual(decision(evaluate("ls | xargs git stash")), "deny")

    def test_permits_safe_compound(self):
        self.assertIsNone(evaluate("cd packages/aegis && git status && git diff --stat | head -20"))
        self.assertIsNone(evaluate('npm test > "$TMPDIR/o.txt" 2>&1; tail -50 "$TMPDIR/o.txt"'))
        self.assertIsNone(evaluate("npm test && tail out.txt"))
        self.assertIsNone(evaluate("if git diff --quiet; then echo clean; fi"))
        self.assertIsNone(evaluate('for f in a b; do git add -- "$f"; done'))

    def test_handles_git_global_options(self):
        self.assertEqual(decision(evaluate("git -C lindorm-monorepo stash")), "deny")
        self.assertEqual(decision(evaluate("git -c core.pager=cat stash")), "deny")
        self.assertEqual(decision(evaluate("git --no-pager --git-dir=.git stash")), "deny")

    def test_two_token_global_options_carry_a_value(self):
        self.assertEqual(decision(evaluate("git --config-env core.pager=P stash")), "deny")
        self.assertEqual(decision(evaluate("git --attr-source HEAD stash")), "deny")
        self.assertEqual(decision(evaluate("git --namespace ns stash")), "deny")
        self.assertIsNone(evaluate("git --config-env core.pager=P log -1"))

    def test_unbalanced_quotes_still_evaluated(self):
        self.assertEqual(decision(evaluate("git stash 'oops")), "deny")


class ScannerTests(unittest.TestCase):
    def test_control_escapes_decode_as_bash_does(self):
        self.assertEqual(git_guard.ansi_decoded("\\c?"), "\x1f")
        self.assertEqual(git_guard.ansi_decoded("\\cM"), "\r")
        self.assertEqual(git_guard.ansi_decoded("a\\c"), "a\\")

    def test_spans_tile_the_text(self):
        for text in (
            "git commit -F - -- a $(echo \")\") <<'EOF'\nfeat: x\nEOF",
            "echo x # ; git stash",
            'cat <(rm -rf src) > "$OUT" 2>&1 | tail',
            "rm -rf $'src' ${X:-a} `b` \\# a\\",
            "",
        ):
            with self.subTest(text=text):
                starts, ends = [span.start for span in git_guard.spans(text)], [span.end for span in git_guard.spans(text)]
                self.assertEqual(starts, [0] + ends[:-1] if ends else [])
                self.assertEqual(ends[-1:], [len(text)] if text else [])

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

    def test_an_unterminated_span_reaches_the_end_of_the_text_without_raising(self):
        for text in ("$(echo", "${X", "<(echo", ">(echo", "`echo", "$'a", "'a", '"a', '"$(a', "$(a '", "$(a \"", '${X:-"', "$'\\"):
            with self.subTest(text=text):
                spans = list(git_guard.spans(text))
                self.assertEqual(spans[-1].end, len(text))
                self.assertFalse(spans[-1].closed)


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
