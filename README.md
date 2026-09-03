# ai-config

Source of truth for Claude Code configuration under `~/.claude`.

```
apply.sh                   symlinks claude/ into ~/.claude, merges hooks into settings.json
claude/CLAUDE.md           global instructions
claude/hooks.json          hook manifest: event -> [{matcher, script, timeout}]
claude/hooks/              hook scripts
claude/skills/ agents/ rules/
scripts/merge_settings.py  settings.json merge
tests/
```

`./apply.sh` links every owned path, prunes dangling links into this repo, merges the manifest
hooks into `~/.claude/settings.json` and lists foreign entries in the owned dirs. It refuses to
overwrite a file it does not own: a differing file is reported as `CONFLICT` and must be moved
aside by hand. A byte-identical file is adopted as a symlink.

`./apply.sh --check` mutates nothing and exits 0 only when everything is already in place.

Tests: `python3 -m unittest discover -s tests -v` and `bash tests/test_apply.sh`.
