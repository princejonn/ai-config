---
name: issue-triage
description: "Judges one tracker item the user names and readies it without asking them: a thin one — missing a label set, a goal or an acceptance — has those drafted and applied, and a complete one has its evidence, its acceptance lines and its proposal challenged through a review whose fix list it applies. Rules out a duplicate and work the tree already satisfies, posts the brief, plan and design the item needs, holds only a finding the user must decide, and files the question whether the item is ready. Use when asking to triage, tidy, label, challenge or ready a named issue before it is worked on, when a ruling on an item restarts its triage, when an item comes back BLOCKED for a missing acceptance section, or when an item may duplicate another or already be done. Dispatches `reviewer` and `verifier`."
---

# Triage an issue

## Input

One issue number: nothing else names the subject. A repository, `--repo <owner/name>`, then rides on every `gh` call here. `gh issue view <N> --json number,title,labels,body,comments` reads the item; its state is its body and comments read as `issue-next` § Output reads them, and every section below judges that state.

With no number, one question under `## Questions` asks which issue: nothing is listed and nothing is edited.

What leaves this skill is a closed item, one split and waiting on its pieces, or an open one under `question`: held on a finding only the user decides, or asked whether it is ready to deliver as its `## Brief` says — the brief `rules/brief.md` defines, filled from the item. That brief is the standard every draft, edit and ruling below is held to.

## State

An item is thin when it carries no label from one of the three sets `issue-write` § Labels defines, or when `## Goal` or `## Acceptance` is missing from its state or stands empty — the heading with no line under it; complete otherwise.

The run is § Draft for a thin item, then § Duplicate, then § Done — an item closed there takes nothing further — then § Critique, which runs again after every edit until it returns `ACCEPTED`, a finding is held or the item is split, then § Ready. The headings below stand in reading order; this sentence is the order they run.

Nothing here asks the user. Everything found is applied, save the four findings only the user decides, which are held — filed through `issue-question`, the item out of the queue until the ruling restarts this skill: a change to the § Goal or the scope; a sentence `issue-write` § Refuse would name as missing; a choice `rules/decisions.md` does not settle; a finding § Critique's stop rule trips on — a disagreement that survived two critique runs, or a defect two runs in a row each traced to the previous run's edit. A held finding ends the run once every other finding is applied; the restart carries the rulings in § Critique's `Decisions made:` and runs the critique again. A split ends the run too, the original waiting on its pieces per `issue-next` § Skip.

## Draft

- Labels: one from each set the item lacks, read off the item's own text through `issue-write` § Labels.
- Body: the headings `issue-write` § Shape gives, keeping every sentence of the original that still holds and adding only what the shape lacks. A "Done when" sentence already in the text is an acceptance line; the evidence already in the text is the § Why.
- Both are applied before anything else runs: `gh issue edit <N> --add-label <label> --add-label <label>`, then `gh issue edit <N> --body-file <path>`, the file written as `issue-write` § Create step 2 writes one and named as § Ready names one.
- A text too thin for one of the two headings gets no drafted body and no guess: its missing sentence is named as `issue-write` § Refuse names one and held as § Apply's question row says, the labels applied all the same.

## Duplicate

Two Goals are the same outcome when reading both says so — never by scoring their similarity, never by a shared subject alone. `gh issue list --state open --limit 1000 --json number,title,body` and the same call with `--state closed` are the comparison set, read to compare and for nothing else; one with no `## Goal`, on either side, is compared by its title.

- An open match where the named item is the newer is a duplicate: it closes as a duplicate of the original, `gh issue close <N> --duplicate-of <M> --comment <text>`, the comment naming the two Goals read as one outcome, whatever labels it carries, and takes no label.
- An open match where the named item is the older rules nothing: the row reports the pair, both numbers, and the twin is untouched.
- A closed match rules nothing here either. It is the question § Done answers, and the pair goes there.

## Critique

The item goes to a `reviewer`, its model per `skills/deliver/references/tiers.md`, as this brief, in the shape `rules/brief.md` defines:

```text
Goal:            judge item #N — the right change, at a stated cost, observable when done
Item:            #N and its URL
Change-set:      the item's state verbatim, the `## Brief` § Ready drafts from it, and the comparison set § Duplicate gathered
Acceptance:      each § Why claim verifies at the file:line or probe it cites
                 each § Acceptance line names a result that can be observed
                 the § Proposal reaches the § Goal
                 the cost is stated
                 the tier label matches `skills/deliver/references/tiers.md`
                 the § Proposal is one item's work
                 the § Goal is no open or closed item's outcome
                 the `## Brief` fills every `rules/brief.md` field from the item's state
Files in scope:  the files the item cites and `skills/deliver/references/tiers.md`, read-only
Decisions made:  the item's rulings, as `issue-next` § Output fills the field
Verification:    none
Invariant:       none
Instructions:    the absolute paths of this repository's instruction files
Tier:            the item's tier label
Out of scope:    editing this item or any other tracker item
```

Findings come back in the reviewer's fix-list form, and the verdict decides what runs next:

- `ACCEPTED` goes to § Ready.
- `NOT ACCEPTED`: the fix list is applied as one body edit, `gh issue edit <N> --body-file <path>`, the file named as § Ready names one, a line against the `## Brief` applied to § Ready's redraft of it instead, and the critique runs again on the edited state — save for three kinds of finding:
  - against `the § Proposal is one item's work` — split, the pieces the finding names.
  - against `the § Goal is no open or closed item's outcome` — § Duplicate's bullets rule it.
  - one of the four § State holds — held, its line left out of the edit.
- `BLOCKED` says the item's own text cannot fill an acceptance line above: that gap is held.
- Stop rule, the circuit breaker `skills/deliver/references/review-loop.md` gives, read for this loop: a finding the previous run also raised is a disagreement that survived two rounds, held; two runs in a row each finding a defect the previous run's edit introduced trip it, those findings held. No other bound: the loop runs until the verdict is `ACCEPTED`, a finding is held or the item is split.
- A finding a ruling on the item settles is applied as the ruling says, never held.
- A carved-out finding rules as its bullet says, and where that bullet rules nothing — a named-older pair, a closed match § Done did not confirm — it contributes no line to the fix list. A `NOT ACCEPTED` that splits nothing, closes nothing, holds nothing and leaves no line to apply counts as `ACCEPTED`, with no body edit.

## Done

Each acceptance line of the item or its draft goes to a `verifier` as one claim against the tree and `git log`. One `DISPROVEN` or `UNVERIFIABLE` line is not done: the item stays open. When no verdict cites a commit, the item is not done either: it stays open. `VERIFIED` for every line runs `git branch -r --contains <hash>` on each commit the verdicts cite, against the remote-tracking refs as they stand, with no fetch. A branch printed for every commit is done: the item closes with a comment carrying those commits, and the closed twin too when § Duplicate handed one over. Nothing printed for one of them is not done: the item stays open, each commit without a branch unpushed. An item with no acceptance line, in body or draft, has no § Done.

## Ready

Reached when the critique returns `ACCEPTED`. Every file this skill writes — a comment or a body — goes to the session scratchpad with the Write tool as `issue-<N>-<purpose>.md` (`issue-75-brief.md`); a comment is posted with `gh issue comment <N> --body-file <scratchpad file>`, and under each heading the latest comment is the current one.

- `## Brief` — the ten fields `rules/brief.md` defines, in its shape: the six `issue-next` § Output fills, read as it reads them, and Files in scope, Verification, Invariant and Instructions read off the tree, every path repo-relative so the comment names no machine. Drafted before each critique run from the state as it then stands, so § Critique judges it, and posted when the critique returns `ACCEPTED`.
- `## Plan` — for `tier: complex` when the item carries none: the high-level plan, one line per step in order, each with the invariant it keeps; `plan-phases` details it in `deliver`.
- `## Design` — when the item changes a public surface and carries none: `design-surface` runs on the item, and its § Exit posts the comment.

Then the ready question, `Is #N ready to deliver as briefed?`, filed through `issue-question` only when every comment above is posted and no `## Question` on the item is unanswered: its recommendation is ready, linking the `## Brief`, `## Plan` and `## Design` comments the item carries. The ruling is `issue-answer`'s: ready sets `ready` there, and any other ruling restarts this skill with it.

## Apply

One table, one row: the item under one ruling, by precedence — done, duplicate, split, question, ready — and the cells record what this skill did to it.

| number | ruling | labels added | body edits | comments | closed by |
|---|---|---|---|---|---|
| `<N>` | ready | — | — | `## Brief`, `## Question` | — |

The question row and the ready row add no label themselves: each files through `issue-question`, and the item leaves the queue under `question`, the label that filing adds, until `issue-answer` posts a ruling that restarts this skill or sets `ready`. A relation an edit implies is written with the two calls in `issue-write` § Create: a split's pieces as sub-issues of the original, a dependency line as a blocked-by relation on the item that carries it. Every body edit — the draft, a fix list, the split's § Related — takes `ready` off an item that carries it: `gh issue edit <N> --remove-label ready`. A cell a bullet does not name is —.

- done — closed by each commit `<hash>` § Done's verdicts cite, with `matched closed #<K>` when § Duplicate handed a closed twin over: `gh issue close <N> --comment <text>`.
- duplicate — closed by the original, `#<M>`, and no label: `gh issue close <N> --duplicate-of <M> --comment <text>`.
- split — the pieces the finding names are created through `issue-write` from § Create step 2 on, each carrying the original's content alone and no dependency line, each filed as a sub-issue of the original; then `gh issue edit <N> --body-file <path>` gives the original's § Related one `Depends on` line per piece, in the form `issue-write` § Shape gives, with the blocked-by relation each line stands for, so `issue-next` skips it until they close and § Done then closes it against their commits. A piece `issue-write` § Refuse would refuse is held as a question instead, ranked where split stands.
- question — each held finding, filed through `issue-question` on the item; a thin item keeps the labels § Draft applied and has its body drafted on the restart.
- ready — the ready question, filed through `issue-question` as § Ready says; `ready` itself is `issue-answer`'s to add.

## Output

The row, with its ruling and what happened to it. Then one line each: the acceptance lines no verdict returned `VERIFIED` for, each with its verdict; the commits § Done found on no remote branch, each named as unpushed, or that no verdict cited a commit; the pair a match reported, a closed match the verdicts left unconfirmed among them; each critique run with its verdict; and each question filed, with its comment URL.
