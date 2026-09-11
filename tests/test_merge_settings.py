import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "merge_settings.py"
LIVE_MANIFEST = REPO / "claude" / "settings.json"

MANIFEST_HOOKS = {
    "PreToolUse": [
        {"matcher": "Bash", "script": "git-guard.py", "timeout": 10},
        {"matcher": "Edit|Write|NotebookEdit", "script": "write-guard.py", "timeout": 10},
    ],
    "SubagentStop": [{"matcher": "reviewer|reviewer-complex|verifier", "script": "verdict-guard.py", "timeout": 5}],
    "SessionStart": [
        {"matcher": "*", "script": "announce-instructions.py", "timeout": 5},
        {"matcher": "*", "script": "drift-notice.py", "timeout": 10},
    ],
}
LIVE_ATTRIBUTION = {"commit": "", "pr": "", "sessionUrl": False}
LIVE_ALLOW = ["Bash(git commit:*)", "Bash(rm:*)", "Bash(find:*)", "Bash(mv:*)"]
LIVE_ASK = ["Bash(git push:*)"]
MANIFEST = {
    "hooks": MANIFEST_HOOKS,
    "defaults": {
        "attribution": LIVE_ATTRIBUTION,
        "permissions.allow": LIVE_ALLOW,
        "permissions.ask": LIVE_ASK,
    },
}
HOOKS_ONLY_MANIFEST = {"hooks": MANIFEST_HOOKS, "defaults": {}}

LIVE_HOOKS_DIR = "/Users/someone/.claude/hooks"
LIVE_HOOKS = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "command": "python3 /Users/someone/.claude/hooks/git-guard.py", "timeout": 10}
            ],
        },
        {
            "matcher": "Edit|Write|NotebookEdit",
            "hooks": [
                {"type": "command", "command": "python3 /Users/someone/.claude/hooks/write-guard.py", "timeout": 10}
            ],
        },
    ],
    "SubagentStop": [
        {
            "matcher": "reviewer|reviewer-complex|verifier",
            "hooks": [
                {"type": "command", "command": "python3 /Users/someone/.claude/hooks/verdict-guard.py", "timeout": 5}
            ],
        },
    ],
    "SessionStart": [
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": "python3 /Users/someone/.claude/hooks/announce-instructions.py", "timeout": 5}
            ],
        },
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": "python3 /Users/someone/.claude/hooks/drift-notice.py", "timeout": 10}
            ],
        },
    ],
}
LIVE_PERMISSIONS = {"allow": LIVE_ALLOW, "ask": LIVE_ASK}
LIVE_SETTINGS = {"hooks": LIVE_HOOKS, "attribution": LIVE_ATTRIBUTION, "permissions": LIVE_PERMISSIONS}

FOREIGN_HANDLER = {"type": "command", "command": "/usr/local/bin/other-hook", "timeout": 5}


def rendered(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


class MergeSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.settings = self.dir / "settings.json"
        self.manifest = self.dir / "manifest.json"
        self.write_manifest(MANIFEST)

    def write_manifest(self, manifest):
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def run_merge(self, *extra, hooks_dir=LIVE_HOOKS_DIR, manifest=None):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--settings",
                str(self.settings),
                "--hooks-dir",
                hooks_dir,
                "--manifest",
                str(manifest or self.manifest),
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    def read(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def assert_error(self, args=(), message=""):
        proc = self.run_merge(*args)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertIn(message, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        return proc

    def test_missing_file_creates_live_hooks_and_defaults(self):
        proc = self.run_merge(manifest=LIVE_MANIFEST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, f"  settings: updated {self.settings}\n")
        self.assertEqual(self.read(), LIVE_SETTINGS)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), rendered(LIVE_SETTINGS))
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)

    def test_foreign_groups_and_shared_group_handlers_survive(self):
        document = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [FOREIGN_HANDLER]},
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 /old/hooks/git-guard.py", "timeout": 10},
                            {"type": "command", "command": "/usr/local/bin/shared-hook"},
                        ],
                    },
                ],
                "Stop": [{"matcher": "*", "hooks": [FOREIGN_HANDLER]}],
            }
        }
        self.settings.write_text(rendered(document), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        hooks = self.read()["hooks"]
        self.assertEqual(hooks["Stop"], [{"matcher": "*", "hooks": [FOREIGN_HANDLER]}])
        self.assertEqual(
            hooks["PreToolUse"],
            [
                {"matcher": "Bash", "hooks": [FOREIGN_HANDLER]},
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/shared-hook"}]},
                *LIVE_HOOKS["PreToolUse"],
            ],
        )

    def test_second_run_is_identical_and_does_not_write(self):
        self.run_merge()
        self.assertEqual(self.read(), LIVE_SETTINGS)
        first = self.settings.read_text(encoding="utf-8")
        os.utime(self.settings, (1_000_000, 1_000_000))
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  settings: unchanged\n")
        self.assertEqual(self.settings.read_text(encoding="utf-8"), first)
        self.assertEqual(self.settings.stat().st_mtime, 1_000_000)

    def test_stale_owned_entry_replaced_by_basename(self):
        stale = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "python3 /elsewhere/hooks/git-guard.py", "timeout": 3}],
                    },
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": "'/opt/homebrew/bin/python3' '/elsewhere/write-guard.py'"}],
                    },
                ],
                "PostToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /elsewhere/git-guard.py"}]}
                ],
            }
        }
        self.settings.write_text(rendered(stale), encoding="utf-8")
        self.write_manifest(HOOKS_ONLY_MANIFEST)
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read(), {"hooks": LIVE_HOOKS})

    def test_default_added_when_absent(self):
        self.settings.write_text(rendered({"model": "opus"}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = self.read()
        self.assertEqual(list(result), ["model", "hooks", "attribution", "permissions"])
        self.assertEqual(result["attribution"], LIVE_ATTRIBUTION)
        self.assertEqual(result["permissions"], LIVE_PERMISSIONS)

    def test_present_partial_attribution_untouched(self):
        self.settings.write_text(rendered({"attribution": {"commit": "x"}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["attribution"], {"commit": "x"})
        self.assertIn('  "attribution": {\n    "commit": "x"\n  },\n', self.settings.read_text(encoding="utf-8"))

    def test_empty_allow_list_gains_every_manifest_entry(self):
        self.settings.write_text(rendered({"permissions": {"allow": []}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["allow"], LIVE_ALLOW)

    def test_present_permissions_without_allow_or_ask_gains_both(self):
        self.settings.write_text(rendered({"permissions": {"deny": ["Bash(sudo:*)"]}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        permissions = self.read()["permissions"]
        self.assertEqual(list(permissions), ["deny", "allow", "ask"])
        self.assertEqual(permissions, {"deny": ["Bash(sudo:*)"], **LIVE_PERMISSIONS})

    def test_allow_list_gains_missing_manifest_entries_in_manifest_order(self):
        self.settings.write_text(rendered({"permissions": {"allow": ["Bash(ls:*)"]}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["allow"], ["Bash(ls:*)", *LIVE_ALLOW])

    def test_second_merge_leaves_a_merged_allow_list_unchanged(self):
        self.settings.write_text(rendered({"permissions": {"allow": ["Bash(ls:*)"]}}), encoding="utf-8")
        self.run_merge()
        merged = self.settings.read_text(encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  settings: unchanged\n")
        self.assertEqual(self.settings.read_text(encoding="utf-8"), merged)
        self.assertEqual(self.read()["permissions"]["allow"], ["Bash(ls:*)", *LIVE_ALLOW])

    def test_entry_the_user_added_keeps_its_place(self):
        allow = ["Bash(git commit:*)", "Bash(ls:*)", "Bash(rm:*)"]
        self.settings.write_text(rendered({"permissions": {"allow": allow}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["allow"], [*allow, "Bash(find:*)", "Bash(mv:*)"])

    def test_manifest_entry_the_user_removed_comes_back(self):
        allow = ["Bash(git commit:*)", "Bash(find:*)", "Bash(mv:*)"]
        self.settings.write_text(rendered({"permissions": {"allow": allow}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["allow"], [*allow, "Bash(rm:*)"])

    def test_duplicate_in_the_user_list_is_not_deduplicated(self):
        allow = ["Bash(rm:*)", "Bash(rm:*)"]
        self.settings.write_text(rendered({"permissions": {"allow": allow}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            self.read()["permissions"]["allow"],
            [*allow, "Bash(git commit:*)", "Bash(find:*)", "Bash(mv:*)"],
        )

    def test_ask_created_with_the_push_rule_when_absent(self):
        self.settings.write_text(rendered({"permissions": {"allow": ["Bash(ls:*)"]}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["ask"], ["Bash(git push:*)"])

    def test_present_ask_gains_the_push_rule(self):
        self.settings.write_text(rendered({"permissions": {"ask": ["Bash(curl:*)"]}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["ask"], ["Bash(curl:*)", "Bash(git push:*)"])

    def test_present_ask_carrying_the_push_rule_is_untouched(self):
        ask = ["Bash(git push:*)", "Bash(curl:*)"]
        self.settings.write_text(rendered({"permissions": {"ask": ask}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read()["permissions"]["ask"], ask)

    def test_allow_not_array_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b'{"permissions": {"allow": "Bash(ls:*)"}}\n')
        self.assert_error()
        self.assertEqual(self.settings.read_bytes(), b'{"permissions": {"allow": "Bash(ls:*)"}}\n')

    def test_non_object_intermediate_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b'{"permissions": []}\n')
        self.assert_error()
        self.assertEqual(self.settings.read_bytes(), b'{"permissions": []}\n')

    def test_invalid_json_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b"{not json")
        proc = self.assert_error()
        self.assertEqual(proc.stdout, "")
        self.assertEqual(self.settings.read_bytes(), b"{not json")
        self.assertEqual(sorted(os.listdir(self.dir)), ["manifest.json", "settings.json"])

    def test_non_object_json_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b"[]\n")
        self.assert_error()
        self.assertEqual(self.settings.read_bytes(), b"[]\n")

    def test_hooks_not_object_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b'{"hooks": []}\n')
        self.assert_error()
        self.assertEqual(self.settings.read_bytes(), b'{"hooks": []}\n')

    def test_event_not_array_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b'{"hooks": {"PreToolUse": {}}}\n')
        self.assert_error()
        self.assertEqual(self.settings.read_bytes(), b'{"hooks": {"PreToolUse": {}}}\n')

    def test_manifest_not_object_exits_1_and_leaves_file(self):
        self.manifest.write_bytes(b"[]\n")
        self.settings.write_bytes(b"{}\n")
        self.assert_error()
        self.assertEqual(self.settings.read_bytes(), b"{}\n")

    def test_manifest_with_unknown_key_exits_1_and_names_it(self):
        self.write_manifest({**HOOKS_ONLY_MANIFEST, "env": {"FOO": "bar"}})
        self.assert_error(message="unknown keys: env")
        self.assertFalse(self.settings.exists())

    def test_manifest_with_neither_key_exits_1(self):
        self.write_manifest({})
        self.assert_error()
        self.assertFalse(self.settings.exists())

    def test_manifest_hooks_or_defaults_not_object_exits_1(self):
        for manifest in ({"hooks": [], "defaults": {}}, {"hooks": MANIFEST_HOOKS, "defaults": []}):
            with self.subTest(manifest=manifest):
                self.write_manifest(manifest)
                self.assert_error()
                self.assertFalse(self.settings.exists())

    def test_manifest_script_with_slash_exits_1(self):
        hooks = {"PreToolUse": [{"matcher": "Bash", "script": "sub/git-guard.py", "timeout": 10}]}
        self.write_manifest({"hooks": hooks, "defaults": {}})
        self.assert_error()
        self.assertFalse(self.settings.exists())

    def test_unwritable_parent_exits_1_without_traceback(self):
        if os.geteuid() == 0:
            self.skipTest("permission bits do not bind root")
        parent = self.dir / "readonly"
        parent.mkdir()
        self.settings = parent / "settings.json"
        parent.chmod(0o500)
        try:
            proc = self.assert_error()
        finally:
            parent.chmod(0o700)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(os.listdir(parent), [])

    def test_symlinked_settings_written_through(self):
        real = self.dir / "real" / "settings.json"
        real.parent.mkdir()
        self.settings.symlink_to(real)
        self.write_manifest(HOOKS_ONLY_MANIFEST)
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(os.readlink(self.settings), str(real))
        self.assertEqual(real.read_text(encoding="utf-8"), rendered({"hooks": LIVE_HOOKS}))
        self.assertEqual(real.stat().st_mode & 0o777, 0o600)

    def test_preexisting_empty_event_survives(self):
        self.settings.write_text(rendered({"hooks": {"Stop": []}}), encoding="utf-8")
        self.write_manifest(HOOKS_ONLY_MANIFEST)
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read(), {"hooks": {"Stop": [], **LIVE_HOOKS}})

    def test_event_emptied_by_merge_is_deleted(self):
        owned = {"type": "command", "command": "python3 /elsewhere/git-guard.py"}
        document = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [owned]}]}}
        self.settings.write_text(rendered(document), encoding="utf-8")
        self.write_manifest(HOOKS_ONLY_MANIFEST)
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read(), {"hooks": LIVE_HOOKS})

    def test_check_pending_change_writes_nothing_and_exits_1(self):
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "  settings: would change\n")
        self.assertFalse(self.settings.exists())
        self.assertEqual(os.listdir(self.dir), ["manifest.json"])

    def test_check_exits_1_with_would_change_when_only_a_default_is_missing(self):
        self.settings.write_text(rendered({"hooks": LIVE_HOOKS, "attribution": LIVE_ATTRIBUTION}), encoding="utf-8")
        before = self.settings.read_bytes()
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "  settings: would change\n")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_check_exits_1_with_would_change_when_an_allow_entry_is_missing(self):
        permissions = {"allow": ["Bash(git commit:*)", "Bash(rm:*)", "Bash(find:*)"], "ask": LIVE_ASK}
        self.settings.write_text(rendered({**LIVE_SETTINGS, "permissions": permissions}), encoding="utf-8")
        before = self.settings.read_bytes()
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "  settings: would change\n")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_check_exits_0_when_the_user_list_carries_every_manifest_entry(self):
        permissions = {"allow": ["Bash(ls:*)", *LIVE_ALLOW], "ask": LIVE_ASK}
        self.settings.write_text(rendered({**LIVE_SETTINGS, "permissions": permissions}), encoding="utf-8")
        before = self.settings.read_bytes()
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  settings: ok\n")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_check_current_exits_0(self):
        self.settings.write_text(rendered(LIVE_SETTINGS), encoding="utf-8")
        before = self.settings.read_bytes()
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  settings: ok\n")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_top_level_key_order_preserved_and_new_default_appended(self):
        document = {
            "permissions": {"allow": ["Bash(ls:*)"]},
            "model": "opus",
            "hooks": {"Stop": [{"matcher": "*", "hooks": [FOREIGN_HANDLER]}]},
            "env": {"FOO": "bar"},
        }
        self.settings.write_text(rendered(document), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = self.read()
        self.assertEqual(list(result.keys()), ["permissions", "model", "hooks", "env", "attribution"])
        self.assertEqual(result["permissions"], {"allow": ["Bash(ls:*)", *LIVE_ALLOW], "ask": LIVE_ASK})
        self.assertEqual(result["model"], "opus")
        self.assertEqual(result["env"], {"FOO": "bar"})
        self.assertEqual(result["attribution"], LIVE_ATTRIBUTION)
        self.assertEqual(list(result["hooks"].keys()), ["Stop", "PreToolUse", "SubagentStop", "SessionStart"])

    def test_command_uses_bare_python3_and_quotes_path(self):
        proc = self.run_merge(hooks_dir="/tmp/with space/hooks")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        commands = [g["hooks"][0]["command"] for g in self.read()["hooks"]["PreToolUse"]]
        self.assertEqual(
            commands,
            ["python3 '/tmp/with space/hooks/git-guard.py'", "python3 '/tmp/with space/hooks/write-guard.py'"],
        )


if __name__ == "__main__":
    unittest.main()
