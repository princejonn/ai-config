# Tiers

A tier classifies how hard an item is to get right, never its size: a one-line authorization change is complex; a large mechanical rename is standard or trivial. Tie-break to standard; the circuit breaker in `references/review-loop.md` re-tiers an item that proves harder.

- `trivial` — renames, boilerplate, config, straightforward tests, docs. Low ambiguity; blast radius contained to named files; correctness checkable by existing tests or types.
- `standard` — the default: ordinary features, fixes and multi-file work following established patterns.
- `complex` — novel algorithms, subtle concurrency or state, security or privacy boundaries, architectural change, non-obvious failure modes.

## Work contract

| | `trivial` | `standard` | `complex` |
|---|---|---|---|
| Plan | no | no | yes, with invariants and binding stop conditions |
| Brief carries | the shape only | a short approach note | the plan |
| Hand-off evidence | the report per `rules/brief.md` | the report | the report plus the plan's exit checks |

## Review placement

Deterministic checks — tests, types, lint — run at every tier. Complex: a `reviewer` per item. Trivial and standard: one batched `reviewer` over the integrated diff, which also covers the cross-item interaction no per-item review sees.

## Fixes

A fix inherits the tier of the code it touches, runs in a fresh agent window with the invariant ledger in its brief, and lands with a pinning test proved red first (`test` § Red-before-green proof).

## Model

| Tier | Model |
|---|---|
| `trivial` | `sonnet` |
| `standard` | `opus` |
| `complex` | `fable` |

An agent's model is chosen when it is spawned, by the first rung that applies:

1. Circuit-breaker escalation (`references/review-loop.md`), reported to the user when the rounds restart — every `developer`, `researcher` and `reviewer` spawn for the re-tiered item, at `fable`.
2. The user's request, for one spawn or standing until revoked — `developer`, `researcher`, `reviewer`, `tester`, `verifier`, `issue-writer` and the built-in agent types, at the model asked for.
3. The table — `developer`, `researcher` and `reviewer`, at their work's tier: a researcher at its lane's tier per § Research routing, a batched review at the highest tier in its batch, `opus` for any batch holding a standard item, and a review with no item at `standard`.
4. The pin — `tester`, `verifier` and `issue-writer` spawn bare and run their frontmatter `model`; a built-in agent type, which has no frontmatter, the `model: opus` `CLAUDE.md` passes.

`recommender` is on no rung: it spawns bare and always runs `fable`.

## Research routing

A lane enumerates when its answer is a list the sources already contain, and interprets when its answer is a reading those sources have to be weighed for; a lane that does both counts as interpreting.

| Tier | Lane |
|---|---|
| `trivial` | enumerates |
| `standard` | interprets |
| `complex` | interprets for a complex-tier item |

An interpreting lane with no item is standard. A `researcher` report whose Left open names the reading it was asked for re-runs at complex; a report at complex that leaves it open goes to the user.
