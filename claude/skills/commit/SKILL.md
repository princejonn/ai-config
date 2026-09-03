---
name: commit
description: "Commits the reviewed change by pathspec: lists the staged paths, composes a stand-alone Conventional Commits message stating mechanism and reason, commits with `git commit -F - -- <paths>`, and confirms with `git show --name-only`. Use only when the user runs /commit."
disable-model-invocation: true
---

# Commit

## Preconditions

- The review ended `ACCEPTED` on both axes.
- The project's full gate is green, with its printed summary in hand.
- `rules/git.md` holds for the change.

## Steps

1. `git diff --cached --name-only`; compare the staged paths to the item's paths.
2. Stage the item's paths by name.
3. Compose the message per `rules/git.md`.
4. `git commit -F - -- <paths>`, naming the item's paths.
5. `git show --name-only`; confirm the committed paths are the item's.
6. Report the hash and the paths. The branch stays unpushed.
