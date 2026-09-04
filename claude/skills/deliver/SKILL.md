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
- Tier the item, not the file count: a one-line change to an invariant is complex; a 40-file mechanical rename is standard. In doubt, tier upward. A fix inherits the tier of the code it touches.
- A complex-tier item runs `plan` first, and its brief carries the plan.

## Living brief and ledgers

**One living brief per loop**, re-sent whole each round, carrying the invariant ledger and every prior finding filed as **Fixed** (with its pinning test) / **Accepted** (cost taken knowingly) / **Rejected — do not re-propose** / **Escalated** (pre-existing, out of scope).

## Rounds

- Once the work is agreed, run it to the end and report; questions belong to `design` or `plan`.
- A fresh reviewer each round: `/review` with the living brief as its arguments; the developer works the fixes it returns.
- A pre-existing defect never widens the loop: escalate it; if it must be fixed now, close this gate and start it as its own item.
- Nothing skips a step because the change looks small; if a step does not apply, say why.

## Circuit breaker

Two consecutive rounds each surfacing a defect the previous round's fixes introduced or left behind → stop and bring it to the user. So does a disagreement that survives two rounds — that is a design question wearing a review's clothes.

## Parallel dispatch

**Parallel agents are disjoint in what they contend for**, not just the files they edit: one writer per package, one heavy test run at a time, and confirm an agent's work still exists before trusting its green.

Parallel developers run in separate git worktrees (`isolation: worktree` on the Agent tool), so one writer per package is a property of the tree, not a request.

## Before commit

An accepted review is not a passed gate: verify the load-bearing claims yourself before committing. `/commit` is the user's to run.
