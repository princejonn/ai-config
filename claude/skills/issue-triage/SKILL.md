---
name: issue-triage
description: "Judges one tracker item the user names: a thin one — missing a label set, a goal or an acceptance — has those drafted, and a complete one has its evidence, its acceptance lines and its proposal challenged through a review. Rules out a duplicate and work the tree already satisfies, and leaves the item with one ruling: ready, draft, revise, split, duplicate, done or question. Use when asking to triage, tidy, label or challenge a named issue before it is worked on, when an item comes back BLOCKED for a missing acceptance section, or when an item may duplicate another or already be done. Proposes only; the user rules before any edit."
---

# Triage an issue

## Input

One issue number: nothing else names the subject. A repository, `--repo <owner/name>`, then rides on every `gh` call here. `gh issue view <N> --json number,title,labels,body` reads the item.

With no number, one question under `## Questions` asks which issue: nothing is listed and nothing is edited.

What leaves this skill is an item `issue-next` can hand on as the brief fields `rules/brief.md` defines — that is the standard every draft and every ruling below is held to.

## State

An item is thin when it carries no label from one of the three sets `issue-write` § Labels defines, or when `## Goal` or `## Acceptance` is missing from its body or stands empty — the heading with no line under it; complete otherwise.

A thin item takes § Draft, a complete one takes § Critique. Both take § Duplicate and § Done, in the order the sections stand.

## Draft

- Labels: one from each set the item lacks, read off the item's own text through `issue-write` § Labels.
- Body: the headings `issue-write` § Shape gives, keeping every sentence of the original that still holds and adding only what the shape lacks. A "Done when" sentence already in the text is an acceptance line; the evidence already in the text is the § Why.
- A text too thin for one of the two headings takes `issue-write` § Refuse: one question to the user, no guess, and no drafted body.

## Duplicate

Two Goals are the same outcome when reading both says so — never by scoring their similarity, never by a shared subject alone. `gh issue list --state open --limit 100 --json number,title,body` and the same call with `--state closed` are the comparison set, read to compare and for nothing else; one with no `## Goal`, on either side, is compared by its title.

- An open match where the named item is the newer is a duplicate: it takes the `duplicate` label and closes with a comment naming the original, whatever labels it carries.
- An open match where the named item is the older rules nothing: the row reports the pair, both numbers, and the twin is untouched.
- A closed match rules nothing here either. It is the question § Done answers, and the pair goes there.

## Critique

The item goes to `/review` as this brief, in the shape `rules/brief.md` defines:

```text
Goal:            judge item #N — the right change, at a stated cost, observable when done
Item:            #N and its URL
Change-set:      the item's body verbatim, and the comparison set § Duplicate gathered
Acceptance:      each § Why claim verifies at the file:line or probe it cites
                 each § Acceptance line names a result that can be observed
                 the § Proposal reaches the § Goal
                 the cost is stated
                 the tier label matches `skills/deliver/references/tiers.md`
                 the § Proposal is one item's work
                 the § Goal is no open or closed item's outcome
Files in scope:  the files the item cites and `~/.claude/skills/deliver/references/tiers.md`, read-only
Decisions made:  none
Verification:    none
Invariant:       none
Instructions:    the absolute paths of this repository's instruction files
Tier:            the item's tier label
Out of scope:    editing this item or any other tracker item
```

Findings come back in the reviewer's fix-list form, and the verdict is the ruling:

- `ACCEPTED` is ready, with no comment.
- `NOT ACCEPTED` is revise, the fix list as the comment, save for two findings:
  - against `the § Proposal is one item's work` — split, the pieces the finding names.
  - against `the § Goal is no open or closed item's outcome` — § Duplicate's bullets rule it.
- `BLOCKED` says the item's own text cannot fill an acceptance line above: revise, that gap as the comment.
- A carved-out finding rules as its bullet says, and where that bullet rules nothing — a named-older pair, a closed match § Done did not confirm — it contributes no line to the fix list, while every other finding still rules revise.

## Done

Each acceptance line of the item or its draft goes to `/verify` as one claim against the tree and `git log`. `VERIFIED` for every line is done: on the user's word the item closes with a comment carrying the commit the verdicts cite, and the closed twin too when § Duplicate handed one over. One `DISPROVEN` or `UNVERIFIABLE` line is not: the item stays open. An item with no acceptance line, in body or draft, has no § Done.

## Apply

One table, one row: the item under one ruling, by precedence — done, duplicate, split, revise, draft or question, ready. What each ruling puts in the cells:

| number | ruling | labels to add | body edit | duplicate of | done by |
|---|---|---|---|---|---|
| `<N>` | ready | — | — | — | — |
| `<N>` | draft | `bug`, `tier: standard` | replaced | — | — |
| `<N>` | revise | `question` | — | — | — |
| `<N>` | split | — | § Related | — | — |
| `<N>` | duplicate | `duplicate` | — | `#<M>` | — |
| `<N>` | done | — | — | — | `<hash>`, matched closed `#<K>` |
| `<N>` | question | `bug`, `question` | — | — | — |

A revise row and a question row both add `question`, which is out of the queue per `issue-write` § Labels, so `issue-next` hands on no item waiting on its author. The edit that follows an answered question — the draft edit or the split edit — carries `--remove-label question`, so the repaired item is handed on without the user touching the label; after a revise the user takes it off.

A drafted body, a split's piece drafts and the missing sentence of a `question` row are shown under the table; the question itself is asked afterwards under `## Questions`, and an answer restarts once what the question came from — § Draft for a thin item, that piece's `issue-write` draft and then the split edit for a split piece. The user's one ruling over the table is the word `issue-write` § Create step 1 asks for, so those pieces take no second ask; the skill edits nothing before the ruling. Then the ruling alone keys the edit:

- ready — nothing.
- draft — `gh issue edit <N> --add-label <label> --add-label <label>`, then `gh issue edit <N> --body-file <path>`, the file written as `issue-write` § Create writes one.
- revise — `gh issue edit <N> --add-label question`, then `gh issue comment <N> --body-file <path>`, the file carrying the fix list for `NOT ACCEPTED` or the gap for `BLOCKED`.
- split — `gh issue comment <N> --body-file <path>` with the fix list, saying the original returns to the queue when its pieces close and that § Done then closes it against their commits; nothing closes it on its own. The pieces are created through `issue-write` carrying no dependency line, then `gh issue edit <N> --body-file <path>` gives the original's § Related one dependency line naming the pieces, in the form `issue-write` § Shape gives, so `issue-next` skips it until they close. A piece `issue-write` § Refuse would refuse makes the row a question instead, ranked where split stands.
- duplicate — `gh issue edit <N> --add-label duplicate`, then `gh issue close <N> --comment <text>` naming the original.
- done — `gh issue close <N> --comment <text>` carrying the commit § Done's verdicts cite.
- question — the labels § Draft found lacking, if any, and `question`: `gh issue edit <N> --add-label <label> --add-label question`, a complete item adding `question` alone. No body edit.

## Output

The row, with its ruling and what happened to it. Then one line each: the acceptance lines no verdict returned `VERIFIED` for, each with its verdict; the pair a match reported, a closed match the verdicts left unconfirmed among them; and the sentence a question row is missing.
