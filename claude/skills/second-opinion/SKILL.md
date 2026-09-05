---
name: second-opinion
description: "Gets a review of a diff, or a challenge of a plan's premises, from a different model family through the read-only `second-opinion-codex` command, and adjudicates every finding before relaying it. Use before acceptance when author and reviewer share the assumptions that shaped the change, or when a design needs an outside attack. It complements review-change, never replaces it."
---

# Second opinion

## Why

A same-model reviewer shares the author's blind spots. A different model family is a decorrelation seam. Its output is a list of claims, never a verdict.

## Policy

- The user is on a free Codex tier: one attempt per item, never per round, and never a retry loop.
- Codex runs read-only; never approve a request to edit.
- The review verdict stands on its own; this skill adds to it and never gates it.
- Keep the call small: one commit or the uncommitted diff of one item, not a range.

## Packet

Write the packet to a file under `$TMPDIR`; it carries the material alone, and `second-opinion-codex` prepends the mode's contract.

- `diff`: `git diff HEAD` for uncommitted work plus `git diff --no-index -- /dev/null <file>` per untracked file, or `git show <sha>` for one commit.
- `plan`: goal, binding constraints, assumptions, chosen approach, rejected alternatives and why, and the conditions that would invalidate the design.

Name no secret-bearing path in it: a dotenv file, a private key or an `.ssh` path is refused.

## Run

Once, from the repository root, so Codex judges against that repository's own instruction files:

`second-opinion-codex diff --packet "$TMPDIR/packet" --out "$TMPDIR/opinion"`, or `plan` for a plan challenge.

Give the Bash tool `timeout: 600000`, its maximum in milliseconds; the script bounds nothing itself.

- `0`: the findings are in `--out`, the transcript in `--out.stderr`.
- `1`: unavailable — relay the `second-opinion unavailable:` line and stop. `Connection failed` or `certificate was not trusted` is the sandbox, not a quota; report it rather than bypassing the sandbox.
- `2`: the call or the packet was rejected and no attempt was spent — correct it and run once.

## Adjudicate

- Every finding is checked before it reaches the user or a brief: read the code it names, or run `/verify-claim` for a load-bearing one.
- Drop what is disproved, keep what is confirmed, and say which is which.
- You own the verdict, not Codex.

## Output

- Confirmed findings with `file:line`.
- Dropped findings with the disproof.
- The exact command run.
