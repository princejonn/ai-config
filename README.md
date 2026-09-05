# ai-config

[![gate](https://github.com/princejonn/ai-config/actions/workflows/gate.yml/badge.svg)](https://github.com/princejonn/ai-config/actions/workflows/gate.yml)

Source of truth for Claude Code configuration under `~/.claude`, shared with Codex.

```
apply.sh                     symlinks claude/ into ~/.claude and ~/.agents/skills and bin/ into ~/.local/bin, renders ~/.codex/AGENTS.md, merges hooks into settings.json
apply-ts.sh                  symlinks claude/rulesets/typescript/ into <folder>/.claude/rules
lib/links.sh                 link classification, pruning and foreign-entry reporting shared by both apply scripts
bin/second-opinion-codex     one read-only Codex call: packet in, findings out, exit 1 when Codex is unavailable
claude/CLAUDE.md             global instructions
claude/settings.json         manifest: hooks (event -> [{matcher, script, timeout}]) and defaults
claude/hooks/                hook scripts
claude/skills/ agents/ rules/
claude/rulesets/typescript/  rules for TypeScript roots, linked per folder
scripts/merge_settings.py    settings.json merge
scripts/render_agents_md.py  AGENTS.md render
tests/
```

`./apply.sh` links every owned path, prunes dangling links into this repo, merges the manifest
hooks and defaults into `~/.claude/settings.json` and lists foreign entries in the owned dirs. The
defaults turn off commit and PR attribution, allow `git commit`, `rm`, `find` and `mv` without a
prompt and ask before `git push`; `git-guard.py` guards the first three, so the permission layer is
not a second gate. A list default merges by union: the entries a machine lacks are appended and
nothing is ever removed. An object default present, even partial, is left as it is. A
`Bash(git push:*)` entry in a machine's `deny` list must be removed by hand for the ask to take
effect. `apply.sh` refuses to overwrite a file it does not own: a differing file is reported as
`CONFLICT` and must be moved aside by hand. A byte-identical file is adopted as a symlink.

Codex reads the same skills through `~/.agents/skills/<name>` links and the same instructions
through `~/.codex/AGENTS.md`, rendered from `claude/CLAUDE.md` followed by `claude/rules/*.md`
with their frontmatter removed. Blocks between `<!-- claude-only -->` and
`<!-- /claude-only -->` describe Claude's machinery and are left out of the render. The first
line is a marker; a file without it is a `CONFLICT`, and an absent `~/.codex` is skipped.
`CLAUDE_CONFIG_DIR`, `AGENTS_SKILLS_DIR`, `CODEX_HOME` and `CLAUDE_LOCAL_BIN` override the target
paths.

`apply.sh` links `bin/second-opinion-codex` into `~/.local/bin` and prints one `warn:` line when
that directory is not on `PATH`. The `second-opinion` skill calls it and adjudicates what it
returns.

Hooks: `git-guard.py` and `write-guard.py` run on `PreToolUse`; `verdict-guard.py` runs on
`SubagentStop` and sends a `reviewer` back once when its final line is none of `ACCEPTED`,
`NOT ACCEPTED`, `BLOCKED`, and a `verifier` once when its message states none of `VERIFIED`,
`DISPROVEN`, `UNVERIFIABLE`. `announce-instructions.py` runs on `SessionStart` and prints the path
and headings of a repository's `AGENTS.md` when the root `CLAUDE.md` does not import it.
`drift-notice.py` runs on `SessionStart` and prints one line when `./apply.sh --check` reports the
live tree has drifted from the repository. A hook denies or stays silent; it never asks, so a run
reaches its report without a prompt from a hook.

`./apply.sh --check` mutates nothing and exits 0 only when everything is already in place.

`claude/rulesets/typescript/` holds the rules that apply only where TypeScript is written;
each carries a `paths` frontmatter, so Claude Code loads it for matching files only. Claude
Code reads a root's `.claude/rules` from every repo beneath it. `./apply-ts.sh <folder>` links
the set into `<folder>/.claude/rules` with the same `ok`, `link`, `adopt` and `CONFLICT` rules
as `apply.sh`, prunes links to removed set files and lists foreign entries;
`./apply-ts.sh --check <folder>` mutates nothing and exits 0 only when the folder is already
in place.

Tests: `python3 -m unittest discover -s tests -v`, `bash tests/test_apply.sh`,
`bash tests/test_apply_ts.sh`, `bash tests/test_second_opinion.sh` and
`bash tests/test_pressure.sh`.

`bash tests/pressure.sh` checks skill triggering on demand — per skill one prompt that must fire it
and one that must not, through `claude -p` in a scratch project — and spends tokens, so the gate
leaves it out.
