import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "merge_settings.py"
LIVE_MANIFEST = REPO / "claude" / "hooks.json"

MANIFEST = {
    "PreToolUse": [
        {"matcher": "Bash", "script": "git-guard.py", "timeout": 10},
        {"matcher": "Edit|Write|MultiEdit|NotebookEdit", "script": "write-guard.py", "timeout": 10},
    ],
    "SubagentStop": [{"matcher": "*", "script": "verdict-guard.py", "timeout": 5}],
}

LIVE_HOOKS_DIR = "/Users/jonn/.claude/hooks"
LIVE_HOOKS = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "command": "python3 /Users/jonn/.claude/hooks/git-guard.py", "timeout": 10}
            ],
        },
        {
            "matcher": "Edit|Write|MultiEdit|NotebookEdit",
            "hooks": [
                {"type": "command", "command": "python3 /Users/jonn/.claude/hooks/write-guard.py", "timeout": 10}
            ],
        },
    ],
    "SubagentStop": [
        {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": "python3 /Users/jonn/.claude/hooks/verdict-guard.py", "timeout": 5}
            ],
        },
    ],
}

FOREIGN_HANDLER = {"type": "command", "command": "/usr/local/bin/other-hook", "timeout": 5}


def rendered(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


class MergeSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.settings = self.dir / "settings.json"
        self.manifest = self.dir / "hooks.json"
        self.manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

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

    def test_missing_file_creates_live_hooks_block(self):
        proc = self.run_merge(manifest=LIVE_MANIFEST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, f"  settings: updated {self.settings}\n")
        self.assertEqual(self.read(), {"hooks": LIVE_HOOKS})
        self.assertEqual(self.settings.read_text(encoding="utf-8"), rendered({"hooks": LIVE_HOOKS}))
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)

    def test_live_hooks_block_reproduced_exactly(self):
        self.settings.write_text(rendered({"hooks": LIVE_HOOKS}), encoding="utf-8")
        proc = self.run_merge(manifest=LIVE_MANIFEST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  settings: unchanged\n")
        self.assertEqual(self.read()["hooks"], LIVE_HOOKS)

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
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read(), {"hooks": LIVE_HOOKS})

    def test_invalid_json_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b"{not json")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(self.settings.read_bytes(), b"{not json")
        self.assertEqual(sorted(os.listdir(self.dir)), ["hooks.json", "settings.json"])

    def test_non_object_json_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b"[]\n")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertEqual(self.settings.read_bytes(), b"[]\n")

    def test_hooks_not_object_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b'{"hooks": []}\n')
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertEqual(self.settings.read_bytes(), b'{"hooks": []}\n')

    def test_event_not_array_exits_1_and_leaves_file(self):
        self.settings.write_bytes(b'{"hooks": {"PreToolUse": {}}}\n')
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertEqual(self.settings.read_bytes(), b'{"hooks": {"PreToolUse": {}}}\n')

    def test_manifest_not_object_exits_1_and_leaves_file(self):
        self.manifest.write_bytes(b"[]\n")
        self.settings.write_bytes(b"{}\n")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertEqual(self.settings.read_bytes(), b"{}\n")

    def test_manifest_script_with_slash_exits_1(self):
        manifest = {"PreToolUse": [{"matcher": "Bash", "script": "sub/git-guard.py", "timeout": 10}]}
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertFalse(self.settings.exists())

    def test_unwritable_parent_exits_1_without_traceback(self):
        if os.geteuid() == 0:
            self.skipTest("permission bits do not bind root")
        parent = self.dir / "readonly"
        parent.mkdir()
        self.settings = parent / "settings.json"
        parent.chmod(0o500)
        proc = self.run_merge()
        parent.chmod(0o700)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(proc.stderr.startswith("ERROR: "), proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(os.listdir(parent), [])

    def test_symlinked_settings_written_through(self):
        real = self.dir / "real" / "settings.json"
        real.parent.mkdir()
        self.settings.symlink_to(real)
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(os.readlink(self.settings), str(real))
        self.assertEqual(real.read_text(encoding="utf-8"), rendered({"hooks": LIVE_HOOKS}))
        self.assertEqual(real.stat().st_mode & 0o777, 0o600)

    def test_preexisting_empty_event_survives(self):
        self.settings.write_text(rendered({"hooks": {"Stop": []}}), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read(), {"hooks": {"Stop": [], **LIVE_HOOKS}})

    def test_event_emptied_by_merge_is_deleted(self):
        owned = {"type": "command", "command": "python3 /elsewhere/git-guard.py"}
        document = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [owned]}]}}
        self.settings.write_text(rendered(document), encoding="utf-8")
        proc = self.run_merge()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.read(), {"hooks": LIVE_HOOKS})

    def test_check_pending_change_writes_nothing_and_exits_1(self):
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "  settings: would change\n")
        self.assertFalse(self.settings.exists())
        self.assertEqual(os.listdir(self.dir), ["hooks.json"])

    def test_check_current_exits_0(self):
        self.settings.write_text(rendered({"hooks": LIVE_HOOKS}), encoding="utf-8")
        before = self.settings.read_bytes()
        proc = self.run_merge("--check")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "  settings: ok\n")
        self.assertEqual(self.settings.read_bytes(), before)

    def test_top_level_keys_preserved_in_order(self):
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
        self.assertEqual(list(result.keys()), ["permissions", "model", "hooks", "env"])
        self.assertEqual(result["permissions"], {"allow": ["Bash(ls:*)"]})
        self.assertEqual(result["model"], "opus")
        self.assertEqual(result["env"], {"FOO": "bar"})
        self.assertEqual(list(result["hooks"].keys()), ["Stop", "PreToolUse", "SubagentStop"])

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
