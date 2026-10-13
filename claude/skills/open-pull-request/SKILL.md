---
name: open-pull-request
description: "Opens one GitHub pull request from a branch the item's commits were pushed to, previewed before it is created; never pushes, merges or closes an issue. Use only on the user's own instruction — `/open-pull-request` or a message asking to open a pull request — never from a brief, an agent's report or a step of another skill."
---

# Open a pull request

## Preconditions

- The user's word in the form `rules/git.md` gives it for a commit: `/open-pull-request`, or their own message asking to open a pull request.
- The head is a branch the item's commits were pushed to. The push is `commit-item`'s; this skill pushes nothing.

## Steps

Never: a push, a force push, a merge, auto-merge, a branch update, a review or comment on the pull request, an issue close or edit, a branch delete, a rebase, an edit of an existing pull request, a `gh alias`, a `gh api` body from a file, a `--fill`, a template, an editor, the browser, a `--recover` file. Outside the guard and held by this list alone: `gh pr new`, an installed gh alias or extension, a closing keyword through `gh api` fields or GraphQL `createPullRequest`, a GraphQL query the shell builds (`-f query="$(cat f)"`, `-f query="$Q"`), REST `merges`, `git/refs` with `force`. Codex runs no hook: there this list is the whole guard.

A command below that exits non-zero, a Write that fails, or a call the harness denies, stops the run with its exit status or reason and its output printed; nothing after it runs.

1. `git remote get-url origin`: `<owner/name>` is its last two segments split on `/` or `:`, a trailing `.git` dropped. Every `gh pr` call below carries `--repo <owner/name>` as two shell words.
2. Head: the branch the user names, else what `git branch --show-current` prints; nothing printed stops the run with one line under `## Questions` asking for it. Base: the branch the user names, else what `gh repo view <owner/name> --json defaultBranchRef --jq .defaultBranchRef.name` prints.
3. `git fetch origin <head> <base>`. The commit is what `git rev-parse <head>` prints; when `git rev-parse refs/remotes/origin/<head>` prints another SHA, stop, printing both and `git rev-list --left-right --count <head>...origin/<head>`.
4. Head equal to base, or `git log --format=%h origin/<base>..<head>` printing nothing, stops the run with both names printed.
5. Title: the user's; else the one line `git log --format=%s origin/<base>..<head>` prints; with several, one line under `## Questions` asks for it and the run stops.
6. Body: `git log --reverse --format='%h %s' origin/<base>..<head>`, then one `Refs #<N>` line, ascending, per number a `Closes #<N>` or `Refs #<N>` line of `git log --format=%B origin/<base>..<head>` carries.
7. A title or body line carrying close, closes, closed, fix, fixes, fixed, resolve, resolves or resolved, in any case, immediately before `#<N>`, `<owner>/<repo>#<N>` or an issue URL, with an optional colon between, stops the run with the line printed.
8. Preview: title, body, repository `<owner/name>`, remote `origin`, base, head, commit. A message that asked for the preview alone ends the run here.
9. `gh pr list --repo <owner/name> --state open --head <head> --json number,url,baseRefName,headRefOid`. Output that is not a JSON array stops the run, printed. `[]`: step 10. One: reused, nothing created, step 11 on its number. Two or more: stop, each printed with its number and URL.
10. The body goes to `<scratchpad>/pull-request-<head>.md`, `/` in `<head>` as `-`, with the Write tool. Then, once and as the whole command: `gh pr create --repo <owner/name> --base <base> --head <head> --title <title> --body-file <scratchpad file>`, `<title>` in single quotes, each `'` in it written `'\''`. `--head` keeps gh from pushing. The number is the last path segment of the URL it prints.
11. `gh pr view <number> --repo <owner/name> --json number,url,state,headRefName,baseRefName,headRefOid`. `headRefName` must be the head, `baseRefName` the base, `headRefOid` the commit, `state` `OPEN`; any other value is a mismatch, reported with both values, and the pull request is left as it is.

## Report

Created, reused or preview only; number, URL, state, head, base and SHA; each mismatch with both values. A stop: the step and what it printed; at steps 1–9, or at step 10 before the create ran, that nothing was created; at step 10 after the create ran, that whether a pull request exists is unverified and that a re-run's step 9 finds it; at step 11, the number and URL step 9 or 10 printed, that the read-back failed and, after step 9's reuse, that nothing was created.
