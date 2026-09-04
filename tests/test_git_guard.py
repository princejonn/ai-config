import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "git-guard.py")
SPEC = importlib.util.spec_from_file_location("git_guard", HOOK_PATH)
git_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(git_guard)

MONOREPO = "/Users/jonn/Projects/lindorm/lindorm-monorepo"
SERVICES = "/Users/jonn/Projects/lindorm/lindorm-services/services/tyr"
TMPDIR = "/private/tmp/claude-501/abc"

DENIED = (
    "git stash",
    "git stash list",
    "git stash show -p stash@{0}",
    "git stash pop",
    "git reset --hard HEAD~1",
    "git clean -fdx",
    "git checkout .",
    "git checkout main",
    "git checkout -- .",
    "git restore .",
    "git restore --staged -- :/",
    "git switch -f main",
    "git push",
    'git commit -a -m "x"',
    'git commit --no-verify -m "x"',
    'git commit -m "fix: x\n\nCo-Authored-By: X" -- a',
    'eval "git stash"',
    'sh -c "git stash"',
    "$(git stash)",
    "echo `git stash`",
    "git -c alias.s=stash s",
    "xargs git stash",
    "exec git stash",
    "command -p git stash",
    "sudo -u root git stash",
    "env -i git stash",
    "nice -n 5 git stash",
    "git checkout -- ./.",
    "git checkout -- :",
    "git restore -- '**'",
    "git checkout -- ..",
    "git restore -- $PWD",
    f"git checkout -- {MONOREPO}",
    "git --config-env core.pager=P stash",
    "git --attr-source HEAD stash",
    "git -c ALIAS.s=stash s",
)
ASKED = (
    "rm -rf packages/aegis/dist",
    "sudo rm -rf x",
    "git commit --amend --no-edit",
    "git commit -F msg.txt -- a",
    "git commit -C HEAD -- a",
    "find . -name '*.js' -delete",
    "find packages -type d -name dist -exec rm -rf {} +",
    'rm -rf "$TMPDIR/$(echo ../..)"',
    'git commit -m "fix: $MSG" -- a',
)
PERMITTED = (
    "git log --stat",
    "git diff HEAD~1 -- file",
    "git checkout -b feat",
    "git checkout -- path/to/file",
    "git restore --staged -- src/",
    "git restore --staged -- file",
    "git switch main",
    'git commit -m "fix: x" -- packages/aegis',
    'git commit -m"feat: add thing" -- packages/aegis',
    "git commit -F - -- a <<'EOF'\nfix: x\nEOF",
    'git commit -m "chore: hooks" -- .claude/hooks/git-guard.py',
    "git -c core.pager=cat log -1",
    'rm -rf "$TMPDIR/x"',
    "npx tsc",
    "npx tsx script.ts",
    "npm exec -- tsc",
    'npm test > "$TMPDIR/o.txt" 2>&1; tail -50 "$TMPDIR/o.txt"',
    "npm test && tail out.txt",
    "npm --version",
    'git commit -m "docs: RFC 6749 §3.1.1" -- a',
    'git commit -m "feat: source-of-truth repo for Claude Code configuration" -- a',
    "if git diff --quiet; then echo clean; fi",
    'for f in a b; do git add -- "$f"; done',
    'echo "git stash"',
    "find . -name '*.ts' -newer x",
    "xargs -n1 echo",
    "node scripts/build.js",
    "git restore -- ':(top,glob)*'",
    "git status",
    "ls",
)


def bash(command, cwd=MONOREPO):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}}


def decision(result):
    return None if result is None else result["hookSpecificOutput"]["permissionDecision"]


def evaluate(command, cwd=MONOREPO):
    return git_guard.evaluate(bash(command, cwd))


class GitStashTests(unittest.TestCase):
    def test_denies_bare_stash(self):
        self.assertEqual(decision(evaluate("git stash")), "deny")

    def test_denies_stash_pop_and_push(self):
        self.assertEqual(decision(evaluate("git stash pop")), "deny")
        self.assertEqual(decision(evaluate("git stash push -m wip")), "deny")

    def test_denies_stash_list_and_show(self):
        self.assertEqual(decision(evaluate("git stash list")), "deny")
        self.assertEqual(decision(evaluate("git stash show -p stash@{0}")), "deny")


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
                    self.assertEqual(decision(evaluate(f"git {subcommand} -- {spec}")), "deny")
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

    def test_top_glob_pathspec_is_left_alone(self):
        self.assertIsNone(evaluate("git restore -- ':(top,glob)*'"))
        self.assertIsNone(evaluate("git checkout -- ':(top,glob)*.ts'"))

    def test_permits_scoped_relative_pathspecs(self):
        self.assertIsNone(evaluate("git checkout -- ./packages/aegis"))
        self.assertIsNone(evaluate("git restore -- ../packages/aegis"))
        self.assertIsNone(evaluate("git restore -- $PWD/src"))

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
    def test_denies_any_push(self):
        self.assertEqual(decision(evaluate("git push")), "deny")
        self.assertEqual(decision(evaluate("git push --force-with-lease origin HEAD")), "deny")

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
        self.assertIsNone(evaluate("git commit -ma -- packages/aegis"))
        self.assertEqual(decision(evaluate("git commit -Fan.txt -- a")), "ask")


class GitCommitMessageSourceTests(unittest.TestCase):
    def test_asks_when_message_comes_from_a_file(self):
        for command in (
            "git commit -F msg.txt -- a",
            "git commit --file=msg.txt -- a",
            "git commit --file msg.txt -- a",
            "git commit -Fmsg.txt -- a",
            "git commit -qF msg.txt -- a",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_asks_when_message_comes_from_another_commit_or_template(self):
        for command in (
            "git commit -C HEAD -- a",
            "git commit -c HEAD~1 -- a",
            "git commit --reuse-message=HEAD -- a",
            "git commit --reedit-message HEAD -- a",
            "git commit -t tpl.txt -- a",
            "git commit --template=tpl.txt -- a",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_asks_when_message_is_shell_expanded(self):
        for command in (
            'git commit -m "fix: $MSG" -- a',
            'git commit -m "fix: ${MSG}" -- a',
            'git commit -m "fix: `date`" -- a',
            'git commit -m "fix: $(cat msg)" -- a',
            'git commit --message="fix: $MSG" -- a',
            'git commit --message "fix: $MSG" -- a',
            'git commit -qm "fix: $MSG" -- a',
            'git commit -m"fix: $MSG" -- a',
            'git commit -m "fix: cost is $5" -- a',
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_permits_literal_message(self):
        self.assertIsNone(evaluate('git commit -m "fix: x" -- a'))
        self.assertIsNone(evaluate("git commit -m 'fix: x' -m 'body' -- a"))
        self.assertIsNone(evaluate('git commit --message="fix: x" -- a'))

    def test_permits_message_from_stdin(self):
        self.assertIsNone(evaluate("git commit -F - -- packages/aegis <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit --file=- -- packages/aegis <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit -F- -- packages/aegis <<'EOF'\nfix: thing\nEOF"))
        self.assertIsNone(evaluate("git commit -F - -- a <<'EOF'\nfix: x\nEOF"))

    def test_pathspec_after_double_dash_is_not_a_message_source(self):
        self.assertIsNone(evaluate('git commit -m "fix: x" -- -C'))
        self.assertIsNone(evaluate("git commit -F - -- '$dir' <<'EOF'\nfix: x\nEOF"))


class GitCommitAttributionTests(unittest.TestCase):
    def test_denies_each_attribution_line(self):
        for line in (
            "Co-Authored-By: Claude <noreply@anthropic.com>",
            "Claude-Session: url",
            "Generated with tool",
            "generated with tool",
            "🤖 Generated with Claude Code",
            "🤖 robot only",
        ):
            with self.subTest(line=line):
                self.assertEqual(decision(evaluate(f'git commit -m "fix: thing\n\n{line}" -- packages/aegis')), "deny")

    def test_denies_trailer_keys_case_insensitively_and_indented(self):
        for line in ("co-authored-by: X", "CO-AUTHORED-BY: X", "claude-session: url", "  co-authored-by: x"):
            with self.subTest(line=line):
                self.assertEqual(decision(evaluate(f'git commit -m "fix: thing\n\n{line}" -- packages/aegis')), "deny")

    def test_deny_reason_names_the_offending_line(self):
        result = evaluate('git commit -m "fix: thing\n\n  co-authored-by: x" -- packages/aegis')
        self.assertIn("'co-authored-by: x'", result["hookSpecificOutput"]["permissionDecisionReason"])

    def test_product_names_are_not_attribution(self):
        self.assertIsNone(evaluate('git commit -m "feat: source-of-truth repo for Claude Code configuration" -- a'))
        self.assertIsNone(evaluate('git commit -m "fix: thing\n\nAnthropic docs describe this" -- a'))
        self.assertIsNone(evaluate('git commit -m "docs: mention claude code and anthropic" -- a'))

    def test_trailer_key_inside_a_sentence_is_not_attribution(self):
        self.assertIsNone(evaluate('git commit -m "fix: thing\n\nthe hook denies Co-Authored-By: trailers" -- a'))

    def test_denies_single_line_message_that_is_a_trailer(self):
        self.assertEqual(decision(evaluate('git commit -m "Co-Authored-By: x" -- a')), "deny")

    def test_denies_marker_in_heredoc_body(self):
        command = "git commit -F - -- packages/aegis <<'EOF'\nfix: thing\n\nCo-Authored-By: Someone\nEOF"
        self.assertEqual(decision(evaluate(command)), "deny")

    def test_permits_clean_message_with_lowercase_claude_path(self):
        self.assertIsNone(evaluate('git commit -m "chore: hooks" -- .claude/hooks/x.py'))
        self.assertIsNone(evaluate('git commit -m "chore: hooks" -- .claude/hooks/git-guard.py'))

    def test_marker_outside_a_commit_is_ignored(self):
        self.assertIsNone(evaluate('grep -rn "Co-Authored-By" .'))


class GitCommitAskTests(unittest.TestCase):
    def test_asks_on_amend(self):
        self.assertEqual(decision(evaluate("git commit --amend --no-edit")), "ask")

    def test_asks_when_cwd_is_lindorm_services(self):
        self.assertEqual(decision(evaluate('git commit -m "x" -- a', cwd=SERVICES)), "ask")

    def test_asks_when_command_mentions_lindorm_services(self):
        self.assertEqual(decision(evaluate('git -C lindorm-services commit -m "x" -- a')), "ask")

    def test_permits_monorepo_commit(self):
        self.assertIsNone(evaluate('git commit -m "x" -- a', cwd=MONOREPO))

    def test_deny_wins_over_ask(self):
        self.assertEqual(decision(evaluate("git commit --amend -a", cwd=SERVICES)), "deny")
        self.assertEqual(decision(evaluate('git commit -F msg.txt -m "Co-Authored-By: x" -- a')), "deny")


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
            'echo "$(git push)"',
            'sh -c "eval \\"git stash\\""',
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")

    def test_asks_for_rm_inside_a_substitution(self):
        self.assertEqual(decision(evaluate("echo $(rm -rf build)")), "ask")

    def test_depth_limit_stops_recursion(self):
        nested = "git stash"
        for _ in range(5):
            nested = f'sh -c "{nested.replace(chr(34), chr(92) + chr(34))}"'
        self.assertIsNone(evaluate(nested))

    def test_permits_safe_indirection(self):
        self.assertIsNone(evaluate('sh -c "git status"'))
        self.assertIsNone(evaluate("echo $(git rev-parse HEAD)"))
        self.assertIsNone(evaluate("eval ls"))


class RmTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"TMPDIR": TMPDIR})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_asks_on_recursive_rm_outside_temp(self):
        self.assertEqual(decision(evaluate("rm -rf packages/aegis/dist")), "ask")
        self.assertEqual(decision(evaluate("rm -R build")), "ask")
        self.assertEqual(decision(evaluate("rm -fr ./x")), "ask")

    def test_asks_when_any_target_is_outside_temp(self):
        self.assertEqual(decision(evaluate("rm -rf $TMPDIR/x ./y")), "ask")

    def test_asks_on_rm_by_path_or_wrapper(self):
        for command in ("sudo rm -rf x", "/bin/rm -rf x", "command rm -rf x", "timeout 5 rm -rf x", "xargs rm -rf"):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_asks_when_target_escapes_temp(self):
        self.assertEqual(decision(evaluate("rm -rf $TMPDIR/../../../etc")), "ask")
        self.assertEqual(decision(evaluate('rm -rf "${TMPDIR}/../x"')), "ask")
        self.assertEqual(decision(evaluate("rm -rf /tmp/claude/../etc")), "ask")

    def test_asks_when_target_carries_a_substitution(self):
        for command in (
            'rm -rf "$TMPDIR/$(echo ../..)"',
            'rm -rf "$TMPDIR/`echo ../..`"',
            'rm -rf "${TMPDIR:-/}/x"',
            'rm -rf "${TMPDIR}/${X}"',
            'rm -rf "$TMPDIR/${X}"',
            "rm -rf /tmp/claude/$(basename $PWD)",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_asks_when_target_only_shares_a_prefix_string(self):
        self.assertEqual(decision(evaluate("rm -rf /tmp/claudeX")), "ask")
        self.assertEqual(decision(evaluate("rm -rf /private/tmp/claude-evil/x")), "ask")
        self.assertEqual(decision(evaluate(f"rm -rf {TMPDIR}-evil/x")), "ask")

    def test_asks_when_scratchpad_is_relative_or_partial(self):
        self.assertEqual(decision(evaluate("rm -rf ./scratchpad/x")), "ask")
        self.assertEqual(decision(evaluate("rm -rf scratchpad")), "ask")
        self.assertEqual(decision(evaluate("rm -rf /a/scratchpad-old/x")), "ask")

    def test_permits_recursive_rm_under_temp(self):
        self.assertIsNone(evaluate("rm -rf $TMPDIR/out"))
        self.assertIsNone(evaluate('rm -rf "$TMPDIR/x"'))
        self.assertIsNone(evaluate('rm -rf "${TMPDIR}/x"'))
        self.assertIsNone(evaluate("rm -rf /tmp/claude/x /private/tmp/claude/y"))
        self.assertIsNone(evaluate("rm -rf /tmp/claude"))
        self.assertIsNone(evaluate("rm -rf /some/where/scratchpad/x"))
        self.assertIsNone(evaluate("rm -rf /some/where/scratchpad"))

    def test_permits_literal_tmpdir_when_unset_in_environment(self):
        with mock.patch.dict(os.environ, {"TMPDIR": ""}):
            self.assertIsNone(evaluate('rm -rf "$TMPDIR/x"'))
            self.assertEqual(decision(evaluate("rm -rf $TMPDIR/../x")), "ask")

    def test_permits_resolved_tmpdir_value(self):
        self.assertIsNone(evaluate(f"rm -rf {TMPDIR}/out"))
        self.assertIsNone(evaluate(f"rm -rf {TMPDIR}"))

    def test_permits_non_recursive_rm(self):
        self.assertIsNone(evaluate("rm -f packages/aegis/src/x.ts"))


class FindDeleteTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"TMPDIR": TMPDIR})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_asks_when_find_deletes_outside_temp(self):
        for command in (
            "find . -name '*.js' -delete",
            "find -name '*.js' -delete",
            "find packages -type d -name dist -exec rm -rf {} +",
            "find packages -type d -name dist -exec rm -r {} \\;",
            "find . -type d -name dist -execdir rm -fr {} +",
            "find . -type d -name dist -exec rm -R {} +",
            "find -L packages -name dist -delete",
            "find $TMPDIR/x . -delete",
            "find \"$TMPDIR/$(echo ../..)\" -delete",
        ):
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_permits_find_deleting_under_temp(self):
        self.assertIsNone(evaluate("find $TMPDIR/x -name '*.log' -delete"))
        self.assertIsNone(evaluate('find "${TMPDIR}/x" -type d -exec rm -rf {} +'))
        self.assertIsNone(evaluate("find /tmp/claude/x -delete"))
        self.assertIsNone(evaluate("find -L /tmp/claude/x -delete"))
        self.assertIsNone(evaluate("find -f /tmp/claude/x -delete"))

    def test_permits_find_that_does_not_delete(self):
        self.assertIsNone(evaluate("find . -name '*.ts' -newer x"))
        self.assertIsNone(evaluate("find . -name '*.js' -exec rm -f {} +"))
        self.assertIsNone(evaluate("find . -exec grep -l foo {} \\;"))
        self.assertIsNone(evaluate("find . -type f -print0"))


class CompoundCommandTests(unittest.TestCase):
    def test_denies_push_after_and(self):
        self.assertEqual(decision(evaluate("cd packages/aegis && npm test && git push")), "deny")

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
        self.assertEqual(decision(evaluate("git -C lindorm-monorepo push")), "deny")
        self.assertEqual(decision(evaluate("git -c core.pager=cat stash")), "deny")
        self.assertEqual(decision(evaluate("git --no-pager --git-dir=.git stash")), "deny")

    def test_two_token_global_options_carry_a_value(self):
        self.assertEqual(decision(evaluate("git --config-env core.pager=P stash")), "deny")
        self.assertEqual(decision(evaluate("git --attr-source HEAD stash")), "deny")
        self.assertEqual(decision(evaluate("git --namespace ns push")), "deny")
        self.assertIsNone(evaluate("git --config-env core.pager=P log -1"))

    def test_unbalanced_quotes_still_evaluated(self):
        self.assertEqual(decision(evaluate("git push 'oops")), "deny")


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


class DecisionSurfaceTests(unittest.TestCase):
    def test_every_denied_example_is_denied(self):
        for command in DENIED:
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "deny")

    def test_every_asked_example_is_asked(self):
        for command in ASKED:
            with self.subTest(command=command):
                self.assertEqual(decision(evaluate(command)), "ask")

    def test_every_permitted_example_is_silent(self):
        for command in PERMITTED:
            with self.subTest(command=command):
                self.assertIsNone(evaluate(command))

    def test_only_deny_and_ask_are_ever_emitted(self):
        for command in DENIED + ASKED + PERMITTED:
            with self.subTest(command=command):
                result = evaluate(command)
                if result is not None:
                    self.assertIn(decision(result), {"deny", "ask"})
                    self.assertNotIn("allow", json.dumps(result))


class SubprocessTests(unittest.TestCase):
    def test_denies_via_stdin_and_exits_zero(self):
        proc = subprocess.run([sys.executable, HOOK_PATH], input=json.dumps(bash("git push")), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_garbage_stdin_prints_nothing_and_exits_zero(self):
        proc = subprocess.run([sys.executable, HOOK_PATH], input="{{{", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
