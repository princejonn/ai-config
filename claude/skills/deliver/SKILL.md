---
name: deliver
description: "Runs an agreed item to committable code through agents: tiering, one living brief with its ledgers, review rounds to acceptance, a circuit breaker. Use once work is agreed; questions belong to design-surface or plan-phases. Dispatches `developer`, `researcher`, `reviewer`, `tester` and `verifier`."
---

# Deliver

## Loop shape

Explore → plan → implement → verify. Code is committable when a reviewer accepts it:

    developer → reviewer → fixes → developer → reviewer → … ACCEPTED → tester → reviewer (delta) →
    docs → commit

## Intake and tiering

- Tier every item per `references/tiers.md` before it runs: the tier sets whether `plan-phases` runs first, what the brief carries and where review sits.
- A one-liner tiered `trivial` runs `implement` inline; every other item gets a brief.
- A tracker item's brief is the `## Brief` comment `issue-next` hands out, later rulings under `Decisions made:` included. Its paths are repo-relative; the brief written for the agent resolves each against the repository root. For `tier: complex`, the item's latest `## Plan` comment is what `plan-phases` details into the plan the brief carries.
- Before the item runs, inline or dispatched, the brief is checked against the tree. A file it names that is gone, or a premise a `verifier` returns `DISPROVEN` for, contradicts the brief: the contradiction is filed as a question through `issue-question` on the item, `Filed from: deliver § Intake` — the filing takes `ready` off — and nothing runs.

## Living brief and ledgers

**One living brief per item**, carrying the invariant ledger, the deviation ledger and every prior finding filed as **Fixed** (with its pinning test) / **Accepted** (cost taken knowingly) / **Rejected — do not re-propose** / **Escalated** (pre-existing, out of scope). A batched round reads every brief in its batch and files its findings and its artefact under each item it covers; `<round>` counts per item and never restarts.

## Rounds

- Once the work is agreed, run it to the end and report; questions belong to `design-surface` or `plan-phases`.
- Every spawn runs in the background: the orchestrator ends its turn and resumes on the completion notification, so steering arrives mid-run and folds into the running item or the next brief. Steering that changes the nature of the work re-tiers its item as if dispatched fresh.
- A load-bearing claim goes to a `verifier` before it enters a brief or a verdict. Bulk and interpreting reads go to a `researcher` at its model per `references/tiers.md`, and the memo, not the material, enters the brief.
- A fresh `reviewer` each round on the living brief, its model per `references/tiers.md`. The developer works the fixes it returns.
- A `BLOCKED` review names what the brief lacks: complete the brief and re-dispatch; it is not a round and does not count toward the circuit breaker.
- A `NOT ACCEPTED` review opens a round run per `references/review-loop.md`.
- A brief — initial or fix round — that would add a surface, change a behaviour, accept a limitation or extend scope beyond the design the user agreed to is a deviation: record it in the living brief with one concrete example (what happens, under what conditions, what the user observes); when the ruling is the user's, file it through `issue-question` on the item, pause the item and continue the loop with the next; a factual premise inside a ruling goes to a `verifier` before it enters a brief. An item with an open ledger entry is not committed to the working branch until the user rules; the others commit as they are accepted, and the final report leads with the ledger.
- Nothing skips a step because the change looks small; if a step does not apply, say why.

## Interruptions

- The living brief is `<repo>/.tmp/deliver-<item>.md`, never the tree, `<item>` the tracker number or, with none, the first six words of the brief's Goal, lower-cased, each run of characters other than a–z and 0–9 made one hyphen, with no hyphen at either end. Write progress through to it after every item — the brief's status, the item's files — so a resume needs that file and the working tree, never conversation archaeology. `.tmp/` is ignored through `.git/info/exclude`: before the first write under `.tmp/`, when `git check-ignore -q .tmp/` fails, run `printf '.tmp/\n' >> "$(git rev-parse --git-path info/exclude)"`.
- On a session-limit error stop dispatching, pause each item in flight, state the checkpoint (done, in flight, next) and end the turn.
- A pause — on a deviation filed through `issue-question`, a breaker trip that ends the run (`references/review-loop.md`) or a session-limit stop — applies to an item with a tracker reference and changes in the tree. Each command runs on its own: (1) `git switch -c paused/<N>-<k>`, k the item's count of `## Paused` comments plus one; (2) `git add -- <paths>`, the item's paths by name, then `git commit -F - -- <paths> <<'EOF' … EOF` with subject `chore(paused): paused work for #<N>`, a body naming the working branch, what is done and the next step, and footer `Refs #<N>`; (3) `git push origin paused/<N>-<k>`; (4) `git switch <working branch>`. Then a `## Paused` comment on the item — the paused branch, the working branch, what is done and the next step — from a scratchpad file through `gh issue comment <N> --body-file <scratchpad file>`, and `gh issue edit <N> --add-label paused --remove-label ready`.
- Before re-dispatching an interrupted item inspect the tree: a stranded agent's work is usually on disk, so the resume brief is "verify and complete" against the existing diff. A `paused` item resumes after § Intake's check: read its latest `## Paused` comment; `git fetch origin paused/<N>-<k>:paused/<N>-<k>` when the branch is not local; on the session's working branch `git cherry-pick --no-commit paused/<N>-<k>`, which brings the work back uncommitted; a conflicted path keeps its markers and goes into the "verify and complete" brief. `paused` stays until the item closes; a later pause cuts `paused/<N>-<k+1>`.

## Circuit breaker

Per `references/review-loop.md`.

## Parallel dispatch

**Parallel agents are disjoint in what they contend for**, not just the files they edit: one writer per package, one heavy test run at a time, and confirm an agent's work still exists before trusting its green.

Parallel developers run in separate git worktrees (`isolation: worktree` on the Agent tool), so one writer per package is a property of the tree, not a request.

## Before commit

An accepted review is not a passed gate: verify the load-bearing claims yourself, then run `/commit-item` for the item. The order is commit, push, close, per `rules/git.md`. Once the item is closed, `git branch -D paused/<N>-<k>` for each branch `git branch --list 'paused/<N>-*'` prints, and `git push origin --delete paused/<N>-<k>` for each `git ls-remote origin 'refs/heads/paused/<N>-*'` prints. Only the circuit breaker, an open deviation entry and a commit without a tracker reference wait on the user.
