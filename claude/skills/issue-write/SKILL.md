---
name: issue-write
description: "Drafts one tracker item in the shape this repository's items have, labelled for type — bug, feature, enhancement or documentation, with story for one written from the user's side — and for priority and tier, then creates it with `gh issue create`. Use when a discussion with the user yields a finding, a request, an idea or a user story to add as an issue; a description too vague for a goal or an observable acceptance comes back as a question instead of an item. Dispatches `verifier`."
---

# Write an issue

## Input

A title and a description, however rough, from a discussion with the user. The other items the same discussion yields, the rest of the set, come with it for § Check. A finding made during work is raised with the user, not filed. An item is not a brief: it carries what must be true and how that is observed, and the brief `rules/brief.md` defines is written from it later.

## Shape

The body is these five headings, in this order, and nothing else:

```text
## Goal        one paragraph: what is true when the item is done
## Why         the evidence: file:line, probe output, the rule that is violated
## Proposal    the change, concrete enough to brief from
## Acceptance  one line per scenario, in the form `rules/brief.md` gives for Acceptance
## Related     one line per dependency, then the notes
```

A dependency is a line that begins `Depends on #N` after any list marker, several numbers allowed: `Depends on #4, #7`; the line is the readable form of the blocked-by relation § Create writes. Every other line in § Related is a note — out of scope, a sibling, background — and names items freely.

A `story` item keeps the five headings and changes two: § Goal is the three-part statement `As a <who>, I want <what>, so that <why>`, and each § Acceptance line is one Given/When/Then scenario — one line, one observable result, so the Acceptance form above holds. A story spanning several features splits into one issue per feature, the story carrying one `Depends on` line per feature issue. A description that opens `As a …`, and any request for a story, takes this shape and the `story` label beside `feature` or `enhancement`; one that reports a defect is a `bug` in the plain shape, without `story`.

## Labels

One from the type set, one priority, one tier, never two from one set; a type outside the set is refused.

- Type: `bug`; `feature`, one new capability; `enhancement`, a change to a capability that exists; `documentation`, docs alone.
- `story`, beside the type: the angle the item is written from, not a kind of its own (§ Shape).
- Priority: `priority: blocker`, `priority: high`, `priority: medium` or `priority: low` — the tracker's own label descriptions decide which (`gh label list --limit 1000`).
- Tier: `tier: trivial`, `tier: standard` or `tier: complex`, per `skills/deliver/references/tiers.md`.
- Status, never written here: `ready`, taken by `deliver` as it stands; `paused`, started and stopped, handed out after blocker-priority items and before the rest. An open item carries at most one of the two and is in the backlog with neither; a label on a closed item is inert.
- Holds, out of the queue whatever the status, never written here: `question`, waiting on the user's ruling; `parked`, not now, by decision; `blocked`, waiting on something outside the repository; `invalid`, `wontfix`.
- Topic and hint, no effect on the queue: `accessibility`, `good first issue`, `help wanted`.

## Refuse

When the Goal or Acceptance cannot be written from the description, create nothing and return one question under `## Questions` naming the missing sentence: the outcome that is not observable, or the input whose result is unstated.

One refusal per description. If the answer still leaves the same sentence missing, hand the description back as not actionable and stop.

## Check

Every item § Refuse lets through is checked before § Create; one a check stops gets nothing created and returns what stopped it.

- Duplicate: `issue-triage` § Duplicate's comparison set and sameness test, applied to the tracker and to the rest of the set. An open item with the same Goal stops it, returned by number, and so does an item earlier in the set, returned by title; a closed one stops nothing here.
- Evidence: each load-bearing § Why claim goes to a `verifier`. A `DISPROVEN` claim is corrected from the verdict's evidence or struck, and a Goal that rests on a struck claim stops the item, returned with the verdict; an `UNVERIFIABLE` claim stops nothing here, and `issue-triage` § Critique judges it.
- Done: the Goal read against the tree. A file:line that already satisfies it stops the item, returned with it.

A dependent follows its blocker in the set: a blocker stopped as a duplicate is replaced in the dependent's dependency line by the open item it matched, and a blocker refused or stopped otherwise leaves the dependent uncreated too, returned with the blocker's reason.

The critique and a verdict per acceptance line stay `issue-triage`'s, its § Critique and § Done on the created item.

## Create

1. An item is created only out of a discussion with the user, which is the word for every item it yields; nothing creates one automatically (`rules/git.md`).
2. Write the body to the session scratchpad with the Write tool, as `issue-<slug>.md` with the slug from the title — never a shell heredoc, never a fixed name.
3. `gh issue create --title <t> --label <type> --label <priority> --label <tier> --body-file <scratchpad file>`, with a further `--label story` when the item is one.
4. The relations the item stands in, node ids from `gh issue view <N> --json id --jq .id`:
   - a piece of a split, under the item it was split from: `gh api graphql -f query='mutation { addSubIssue(input: {issueId: "<parent id>", subIssueId: "<piece id>"}) { issue { number } subIssue { number } } }'`
   - one per number a `Depends on #N` line names: `gh api graphql -f query='mutation { addBlockedBy(input: {issueId: "<item id>", blockingIssueId: "<blocker id>"}) { issue { number } blockingIssue { number } } }'`
5. For `tier: complex`, when the discussion settled the plan: a `## Plan` comment in the shape `issue-triage` § Ready gives, its file written as step 2 writes one and named as `issue-triage` § Ready names one, posted with `gh issue comment <N> --body-file <scratchpad file>`. A plan the discussion left open is `issue-triage`'s to write.

## Output

The item's number and its URL, with the relations step 4 wrote and the `## Plan` comment step 5 posted. Or, with nothing created, the question § Refuse returns or what stopped the item in § Check.
