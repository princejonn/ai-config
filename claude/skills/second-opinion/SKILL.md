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
- Inside the Claude Code sandbox every `codex` command carries `CODEX_CA_CERTIFICATE=/etc/ssl/cert.pem`. Codex never runs commands here: its own sandbox cannot start inside Claude Code's, so the material it needs goes in the prompt. A `Connection failed` or `certificate was not trusted` before any Codex output is the sandbox, not a quota: report it rather than bypassing the sandbox.

## Availability

- The user is on a free Codex tier. One attempt per item, never per round, and never a retry loop.
- A non-zero exit, or output that says the usage limit, quota or rate limit is reached, or that login is required, means the second opinion is unavailable: report `second-opinion unavailable: <first stderr line>` and stop.
- The review verdict stands on its own; this skill adds to it and never gates it.
- Keep the call small: review one commit or the uncommitted diff of one item, not a range.

## Diff review

- Write the diff to a file under `$TMPDIR`: `git diff HEAD` for uncommitted work plus `git diff --no-index -- /dev/null <file>` per untracked file, or `git show <sha>` for one commit.
- Build the packet: one paragraph naming the repository's languages and conventions, the instruction "Do not run any commands; the diff is complete. Report only concrete defects, each with file and line, severity P1-P3, and the mechanism. No summary, no praise.", then the diff.
- Run `CODEX_CA_CERTIFICATE=/etc/ssl/cert.pem codex exec -s read-only --ignore-user-config - < packet`, stdout and stderr to files under `$TMPDIR`; stdout carries only the final message.

## Plan challenge

- `CODEX_CA_CERTIFICATE=/etc/ssl/cert.pem codex exec -s read-only --ignore-user-config "<packet>"` with a packet carrying: goal, binding constraints, assumptions, chosen approach, rejected alternatives and why, and the conditions that would invalidate the design.
- Ask for `REFUTE` (a premise that is false), `MISSING` (a constraint not considered) and `ALTERNATIVE` (a cheaper approach) items only; no score, no summary.

## Adjudicate

- Every finding is checked before it reaches the user or a brief: read the code it names, or run `/verify` for a load-bearing one.
- Drop what is disproved, keep what is confirmed, and say which is which.
- You own the verdict, not Codex.

## Output

- Confirmed findings with `file:line`.
- Dropped findings with the disproof.
- The exact command run.
