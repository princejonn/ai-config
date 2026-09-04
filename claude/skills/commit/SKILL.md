---
name: commit
description: "Commits one accepted item by pathspec with a stand-alone Conventional Commits message and closes its GitHub issue. Use as soon as a review has ended ACCEPTED, the gate is green and the item carries a tracker reference; with no reference, only on the user's word."
---

# Commit

## Preconditions

- The review ended `ACCEPTED`.
- The project's full gate is green, with its printed summary in hand.
- `rules/git.md` holds for the change.
- No entry for this item stands open in the deviation ledger.
- The brief's `Item:` line carries a tracker reference, or the user's word per `rules/git.md` is in hand.

## Steps

1. `git diff --cached --name-only`; compare the staged paths to the item's paths and unstage anything else.
2. Stage the item's paths by name.
3. Compose the message per `rules/git.md`; when there is a reference, the footer carries it: `Closes #N` for an issue in this repository, `Refs: KEY-123` or the URL otherwise.
4. `git commit -F - -- <paths>` with a heredoc.
5. `git show --name-only`; confirm the committed paths are the item's.
6. A GitHub issue: `gh issue close <n> --comment "<hash> <subject>"`; a failed close is reported the same way as another tracker's reference. Another tracker: report the reference for the user to close. None: nothing to close.
7. Report the hash, the paths and, when one exists, the closed or reported reference. The branch stays unpushed.
