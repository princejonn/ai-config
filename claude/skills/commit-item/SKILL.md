---
name: commit-item
description: "Commits one accepted change-set by pathspec with a stand-alone Conventional Commits message and its tracker footer. Use as soon as a review has ended ACCEPTED, the gate is green and the item carries a tracker reference; with no reference, only on the user's word."
---

# Commit

## Preconditions

- The review ended `ACCEPTED`.
- The project's full gate is green, with its printed summary in hand.
- `rules/git.md` holds for the change.
- No entry for this item stands open in the deviation ledger.
- The brief's `Item:` line carries a tracker reference, or the user's word per `rules/git.md` is in hand.
- The brief says whether this change-set completes the item; unsaid, the footer is `Refs #N`.

## Steps

1. `git diff --cached --name-only`; compare the staged paths to the item's paths and unstage anything else.
2. Stage the item's paths by name.
3. Compose the message per `rules/git.md`; when there is a reference, the footer carries it: `Closes #N` only on the commit that completes the item, `Refs #N` on a change-set that leaves it open, `Refs: KEY-123` or the URL for another tracker.
4. `git commit -F - -- <paths>` with a heredoc.
5. `git show --name-only`; confirm the committed paths are the item's.
6. Report the hash, the paths and, when one exists, the tracker reference. The branch stays unpushed; the issue closes after the push, per `rules/git.md`.
