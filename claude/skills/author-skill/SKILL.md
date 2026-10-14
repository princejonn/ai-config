---
name: author-skill
description: "Writes or revises a skill, rule or agent in the ai-config repo — description as a trigger, body as the procedure, one home per rule — and proves it with the gate and, when triggering text changes, a pressure run. Use when adding, splitting or rewording a skill, rule or agent, or when a skill did not fire or was followed from its description alone."
---

# Author a skill

## Where things live

- Skills carry procedure.
- Rules carry conventions, path-scoped when tied to a file type.
- CLAUDE.md carries only what is undiscoverable and global.
- Agents are frontmatter plus two sentences.

## Description

- Third person, what and when, trigger terms in the words the user will type.
- Never the workflow: a description that narrates steps gets followed instead of the body.
- Under 1024 characters, well under in practice.
- A skill whose body names an agent — which it does only to dispatch it — ends its description with ``Dispatches `<a>` and `<b>`.``, each agent its body names and no other.

## Body

- A skill carries no orchestration: it handles the one thing named, delegating a step where it must — the steps it delegates, their count, order and bound, and the skill its output goes to, are its to name — and it never picks a subject or runs a skill on another; what else runs, and on what, is the chat's call. It must only where it writes on that step's result itself — a comment, an issue, a label. Exempt by design: `deliver`, whose procedure is that schedule, and the queue readers — `issue-next`, and `issue-answer` given no number — whose subject is the tracker's next item. No skill is a fork.
- Under 200 lines.
- A skill may carry `references/*.md` for protocol its body only names, read on demand; the 200-line rule applies to `SKILL.md`.
- Input, method, output, and a done-condition; a stop rule wherever the procedure can loop.
- A skill an agent preloads states in its Input that the brief takes the shape `rules/brief.md` defines.

## One home

A sentence lives in exactly one file.

## Prove it

- `bash tests/gate.sh`.
- Only when a description or a `claude/CLAUDE.md` routing row changes, the pressure run for that skill: `bash tests/pressure.sh --only <skill>` runs one prompt that should fire the skill and one that should not through a fresh `claude -p` in a scratch project; a skill with no pair in the script gets one first. Record both lines.
- When triggering is wrong, change the description, not the body.

## Portability

Only `name` and `description` reach Codex; Claude-only keys are ignored there. A skill that must stay user-only in Codex ships `agents/openai.yaml` beside its SKILL.md, with a `policy` block setting `allow_implicit_invocation: false`.

## Output

- Files changed.
- The test summary.
- Both pressure-run prompts with their outcomes, when § Prove it ran one.
