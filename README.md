# ai-config

Source of truth for Claude Code configuration under `~/.claude`, shared with Codex.

```
apply.sh                     symlinks claude/ into ~/.claude and ~/.agents/skills, renders ~/.codex/AGENTS.md, merges hooks into settings.json
claude/CLAUDE.md             global instructions
claude/hooks.json            hook manifest: event -> [{matcher, script, timeout}]
claude/hooks/                hook scripts
claude/skills/ agents/ rules/
scripts/merge_settings.py    settings.json merge
scripts/render_agents_md.py  AGENTS.md render
tests/
```

`./apply.sh` links every owned path, prunes dangling links into this repo, merges the manifest
hooks into `~/.claude/settings.json` and lists foreign entries in the owned dirs. It refuses to
overwrite a file it does not own: a differing file is reported as `CONFLICT` and must be moved
aside by hand. A byte-identical file is adopted as a symlink.

Codex reads the same skills through `~/.agents/skills/<name>` links and the same instructions
through `~/.codex/AGENTS.md`, rendered from `claude/CLAUDE.md` followed by `claude/rules/*.md`
with their frontmatter removed. The first line is a marker; a file without it is a `CONFLICT`,
and an absent `~/.codex` is skipped. `CLAUDE_CONFIG_DIR`, `AGENTS_SKILLS_DIR` and `CODEX_HOME`
override the target paths.

Hooks: `git-guard.py` and `write-guard.py` run on `PreToolUse`; `verdict-guard.py` runs on
`SubagentStop` and sends a `reviewer` back once when its message states neither `ACCEPTED` nor
`NOT ACCEPTED`, and a `verifier` once when it states none of `VERIFIED`, `DISPROVEN`, `UNVERIFIABLE`.

`./apply.sh --check` mutates nothing and exits 0 only when everything is already in place.

Tests: `python3 -m unittest discover -s tests -v` and `bash tests/test_apply.sh`.
