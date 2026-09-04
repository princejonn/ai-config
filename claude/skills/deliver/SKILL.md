---
name: deliver
description: "Runs an agreed item to committable code through agents: tiering, one living brief with its ledgers, review rounds to acceptance, a circuit breaker. Use once work is agreed; questions belong to design or plan."
---

# Deliver

## Loop shape

Explore → plan → implement → verify. Code is committable when a reviewer accepts it:

    developer → reviewer → fixes → developer → reviewer → … ACCEPTED → tester → reviewer (delta) →
    docs → commit

## Intake and tiering

- A one-sentence diff runs `implement` directly; anything beyond it gets a brief.
- Tier the item per `references/tiers.md`: the tier sets whether `plan` runs first, what the brief carries and where review sits.

## Living brief and ledgers

**One living brief per loop**, carrying the invariant ledger, the deviation ledger and every prior finding filed as **Fixed** (with its pinning test) / **Accepted** (cost taken knowingly) / **Rejected — do not re-propose** / **Escalated** (pre-existing, out of scope).

## Rounds

- Once the work is agreed, run it to the end and report; questions belong to `design` or `plan`.
- Every spawn runs in the background: the orchestrator ends its turn and resumes on the completion notification, so steering arrives mid-run and folds into the running item or the next brief. Steering that changes the nature of the work re-tiers its item as if dispatched fresh.
- A load-bearing claim goes through `/verify` before it enters a brief or a verdict. Bulk reading goes through `/research`, and the memo, not the material, enters the brief.
- A fresh reviewer each round: `/review` with the living brief as its arguments; the developer works the fixes it returns.
- A `BLOCKED` review names what the brief lacks: complete the brief and re-dispatch; it is not a round and does not count toward the circuit breaker.
- A `NOT ACCEPTED` review opens a round run per `references/review-loop.md`.
- A brief — initial or fix round — that would add a surface, change a behaviour, accept a limitation or extend scope beyond the design the user agreed to is a deviation: record it in the living brief with one concrete example (what happens, under what conditions, what the user observes), continue with items that do not depend on it, and park only an item whose correctness depends on the ruling. An item with an open ledger entry is not committed until the user rules; the others commit as they are accepted, and the final report leads with the ledger.
- Nothing skips a step because the change looks small; if a step does not apply, say why.

## Interruptions

- Write progress through after every item — the brief's status, the item's files — so a resume needs the brief and the working tree, never conversation archaeology.
- On a session-limit error stop dispatching, state the checkpoint (done, in flight, next) and end the turn.
- Before re-dispatching an interrupted item inspect the tree: a stranded agent's work is usually on disk, so the resume brief is "verify and complete" against the existing diff.

## Circuit breaker

Per `references/review-loop.md`.

## Parallel dispatch

**Parallel agents are disjoint in what they contend for**, not just the files they edit: one writer per package, one heavy test run at a time, and confirm an agent's work still exists before trusting its green.

Parallel developers run in separate git worktrees (`isolation: worktree` on the Agent tool), so one writer per package is a property of the tree, not a request.

## Before commit

An accepted review is not a passed gate: verify the load-bearing claims yourself, then run `/commit` for the item. Only the circuit breaker, an open deviation entry and a commit without a tracker reference wait on the user.
