---
name: issue-triage
description: "Repairs the open tracker items the queue cannot use — no type, priority or tier label, or a body missing its goal or its acceptance — and rules out two conditions on the way: an item that duplicates another and an item the tree already satisfies. Use when asking to triage, tidy, label or clean up the issue backlog, when an item comes back BLOCKED for a missing acceptance section, or when the tracker may hold a duplicate or work already done. Proposes only; the user rules before any edit."
---

# Triage the issue queue

## Input

What leaves this skill is an item `issue-next` can hand on as the brief fields `rules/brief.md` defines — that is the standard every draft below is held to. Input is none; or a repository, `--repo <owner/name>`, which then rides on every `gh` call here; or one issue number, which triages that item alone.

## Select

`gh issue list --state open --limit 100 --json number,title,labels,body`. An item is uncategorised when it carries no label from one of the three sets `issue-write` § Labels defines, or when its body lacks `## Goal` or `## Acceptance`. The uncategorised items are the subjects of every section below; every other open item and the closed list are what those sections compare against, and take no draft.

## Draft

Per uncategorised item:

- Labels: one from each set the item lacks, read off the item's own text through `issue-write` § Labels.
- Body: the headings `issue-write` § Shape gives, keeping every sentence of the original that still holds and adding only what the shape lacks. A "Done when" sentence already in the text is an acceptance line; the evidence already in the text is the § Why.
- A text too thin for one of the two headings takes `issue-write` § Refuse: one question to the user, no guess, and no drafted body for that item.

## Duplicate

Two Goals are the same outcome when reading both says so — never by scoring their similarity, never by a shared subject alone. `gh issue list --state closed --limit 100 --json number,title,body` is the closed list; on either side an item with no `## Goal` is compared by its title.

- An open match is a duplicate: report the pair as both numbers, newer first; on the user's word the newer one takes the `duplicate` label and closes with a comment naming the original, whatever labels it carries.
- A closed match rules nothing here. It is the question § Done answers, and the pair goes there.

## Done

Each acceptance line of the item or its draft goes to `/verify` as one claim against the tree and `git log`. `VERIFIED` for every line is done: on the user's word the item closes with a comment carrying the commit the verdicts cite, and the closed twin too when § Duplicate handed one over. One `DISPROVEN` or `UNVERIFIABLE` line is not: the item stays open. An item with no acceptance line, in body or draft, has no § Done.

## Parallel

More than three uncategorised items: § Draft and § Duplicate run as one `/research-complex` lane per item, all forked in one message. Each brief carries the item's full text and the titles and Goals of the items § Duplicate lists, so the lane opens no tracker. Files in scope carries the absolute paths of `~/.claude/skills/issue-write/SKILL.md` and `~/.claude/skills/deliver/references/tiers.md`, the vocabulary the lane applies. The brief's Acceptance names what the memo's Findings carry: one § Apply row, the drafted body, and for a refused item the one missing sentence as a question. The `/verify` lanes of § Done follow. These two are the only lanes: nothing else is dispatched, and what comes back is collected, not redrafted.

## Apply

One table first, carrying every proposed change:

| number | labels to add | body replaced | duplicate of | done by |
|---|---|---|---|---|
| `<N>` | `bug`, `tier: standard` | yes | — | — |
| `<M>` | `duplicate` | no | `#<N>` | — |
| `<K>` | — | no | — | `<hash>`, matched closed `#<J>` |

A body already in `issue-write` § Shape is `body replaced: no`; a refused item is `body replaced: question`. The missing sentence of a `question` row is shown under the table for context only: the ruling covers its labels, the row skips the body edit, and the question itself is asked afterwards under `## Questions`, one per message, where an answer restarts § Draft for that item once. The user rules once, over the whole table; the skill edits nothing before the ruling. Then, per ruled row:

- `gh issue edit <N> --add-label <label> --add-label <label>`, `duplicate` among them for a duplicate row
- `gh issue edit <N> --body-file <path>`, the file written as `issue-write` § Create writes one; a row closing as a duplicate or as done skips this edit
- `gh issue close <N> --comment <text>`, the comment naming the original for a duplicate, the commit for a done item with the closed twin that matched it, and both when the row is both

A row the user does not rule on is edited in no way: the item stays as it is and § Output lists it unruled.

## Output

The table again, each row carrying what happened to it. Then one line each: the acceptance lines no verdict returned `VERIFIED` for, each with its verdict; the related pairs, a closed match those lines left unconfirmed; the rows left unruled; and the items left as questions, each with the sentence it is missing.
