# Tiers

A tier classifies an item's risk, never its file count: a one-line authorization or data-loss change is complex; a large mechanical rename is standard or trivial. Tie-break upward.

- `trivial` — renames, boilerplate, config, straightforward tests, docs. Low ambiguity; blast radius contained to named files; correctness checkable by existing tests or types.
- `standard` — the default: ordinary features, fixes and multi-file work following established patterns.
- `complex` — novel algorithms, subtle concurrency or state, security or privacy boundaries, architectural change, high blast radius, non-obvious failure modes.

## Work contract

| | `trivial` | `standard` | `complex` |
|---|---|---|---|
| Plan | no | no | yes, with invariants and binding stop conditions |
| Brief carries | the shape only | a short approach note | the plan |
| Hand-off evidence | the report per `rules/brief.md` | the report | the report plus the plan's exit checks |

## Review placement

Deterministic checks — tests, types, lint — run at every tier. Complex: a `reviewer-complex` per item. Trivial and standard: one batched `reviewer` over the integrated diff, which also covers the cross-item interaction no per-item review sees.

## Fixes

A fix inherits the tier of the code it touches, runs in a fresh agent window with the invariant ledger in its brief, and lands with a pinning test proved red first (`test` § Red-before-green proof).

## Routing (Claude Code)

| Tier | Developer | Reviewer |
|---|---|---|
| `trivial` | `developer-trivial` | `reviewer` |
| `standard` | `developer` | `reviewer` |
| `complex` | `developer-complex` | `reviewer-complex` |

## Research routing (Claude Code)

A lane enumerates when its answer is a list the sources already contain, and interprets when its answer is a reading those sources have to be weighed for; a lane that does both is complex.

| Tier | Lane | Agent |
|---|---|---|
| `trivial` | enumerates | `researcher-trivial` |
| `complex` | interprets | `researcher-complex` |

A suffix on an agent's name says its tier, never its model, and an unmarked name is the default tier; `max` is deliberately unused.
