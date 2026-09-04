---
name: second-opinion
description: "Gets a review of a diff, or a challenge of a plan's premises, from a different model family by running the Codex CLI read-only, and verifies each finding before relaying it. Use before acceptance when author and reviewer share the assumptions that shaped the change, or when a design needs an outside attack. Requires the codex CLI; it complements review, never replaces it."
---

# Second opinion

## Why

A same-model reviewer shares the author's blind spots. A different model family is a decorrelation seam. Its output is a list of claims, never a verdict.

## Preconditions

- `codex` on PATH.
- Codex runs read-only: only the commands and flags below; never a flag that grants writes; never approve a Codex request to edit.

## Availability

- The user is on a free Codex tier. One attempt per item, never per round, and never a retry loop.
- A non-zero exit, or output that says the usage limit, quota or rate limit is reached, or that login is required, means the second opinion is unavailable: report `second-opinion unavailable: <first stderr line>` and stop.
- The review verdict stands on its own; this skill adds to it and never gates it.
- Keep the call small: review one commit or the uncommitted diff of one item, not a range.

## Diff review

- Exactly one target: `codex exec -s read-only --ignore-user-config review --uncommitted`, or `… review --base <branch>`, or `… review --commit <sha>`.
- Custom instructions replace the target (`… review "<instructions>"`) and cannot be combined with one.
- Redirect stdout and stderr to files under `$TMPDIR` and read them; stdout carries only the final message.

## Plan challenge

- `codex exec -s read-only --ignore-user-config "<packet>"` with a packet carrying: goal, binding constraints, assumptions, chosen approach, rejected alternatives and why, and the conditions that would invalidate the design.
- Ask for `REFUTE` (a premise that is false), `MISSING` (a constraint not considered) and `ALTERNATIVE` (a cheaper approach) items only; no score, no summary.

## Adjudicate

- Every finding is checked before it reaches the user or a brief: read the code it names, or run `/verify` for a load-bearing one.
- Drop what is disproved, keep what is confirmed, and say which is which.
- You own the verdict, not Codex.

## Output

- Confirmed findings with `file:line`.
- Dropped findings with the disproof.
- The exact command run.
