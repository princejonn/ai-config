# Review loop

Read when a review returns `NOT ACCEPTED`. Each round:

- **A reviewed baseline and a minimal diff, regenerated every round.** When partial attempts have drifted the tree, reset to the last reviewed state and re-derive the smallest diff before looping: review depth is spent on surface, so surface shrinks first.
- **One living brief, re-sent whole.** Adjudications accumulate in it; a fresh prompt per round throws them away and invites re-litigated findings.
- **A unique output artefact per round.** Concurrent rounds on one path interleave.
- **Re-review scope is the reviewer's contract**, `review-change` § Re-review and the adjudication ledger. The change-set-wide audit belongs to the first round and runs again only after a gate closes and its change-set lands — a new item against the landed tree.
- **A pre-existing defect is Escalated**: recorded, fixed after this gate closes. If it must be fixed now, that ruling closes the current gate: the green change-set is landed and the adopted work starts as its own item against the new baseline.
- **A mechanism-wide fix** ("every site of X") carries an exhaustive site list produced by a `/verify-claim` lane, with a per-site disposition the fix returns completed; the unswept remainder is the next round's finding.
- **Circuit breaker.** Two consecutive rounds each surfacing a defect the previous round's fixes introduced or left behind — a regression and an unswept remainder count equally — trip the breaker; so does a disagreement that survives two rounds, a design question wearing a review's clothes. At trivial or standard tier a defect trip re-tiers the item whose fixes carried the defect to complex, the rest of the batch continuing at its tier: reset that item to the last reviewed baseline and restart its rounds with `developer-complex` and `reviewer-complex` on the living brief. A defect trip on that pair, and a disagreement trip at any tier, end the run with a report.
