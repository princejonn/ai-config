---
name: author-skill
description: "Writes or revises a skill, rule or agent in the ai-config repo — description as a trigger, body as the procedure, one home per rule — and proves it with the payload test and a pressure run. Use when adding, splitting or rewording a skill, rule or agent, or when a skill did not fire or was followed from its description alone."
---

# Author a skill

## Where things live

- Skills carry procedure.
- Rules carry conventions, path-scoped when tied to a file type.
- CLAUDE.md carries only what is undiscoverable and global.
- Agents are frontmatter plus two sentences; a fork target preloads no skill (the body would arrive twice).

## Description

- Third person, what and when, trigger terms in the words the user will type.
- Never the workflow: a description that narrates steps gets followed instead of the body.
- Under 1024 characters, well under in practice.

## Body

- Under 200 lines.
- Input, method, output, and a done-condition; a stop rule wherever the procedure can loop.
- A fork skill states that its brief arrives as `$ARGUMENTS` and carries everything it needs cold.

## One home

A sentence lives in exactly one file. `tests/test_payload.py` pins the shared phrases; when a rule moves, move its phrase.

## Prove it

- `python3 -m unittest discover -s tests`, then a pressure run: a fresh `claude -p` in a scratch project with one prompt that should fire the skill and one that should not. Record both.
- When triggering is wrong, change the description, not the body.

## Portability

Only `name` and `description` reach Codex; Claude-only keys are ignored there. A skill that must stay user-only in Codex ships `agents/openai.yaml` beside its SKILL.md; `claude/skills/commit/agents/openai.yaml` is the pinned example.

## Output

- Files changed.
- The test summary.
- Both pressure-run prompts with their outcomes.
