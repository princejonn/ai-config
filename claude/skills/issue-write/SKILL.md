---
name: issue-write
description: "Drafts one tracker item in the shape this repository's items have, labelled for type — bug, feature, enhancement or documentation, with story for one written from the user's side — and for priority and tier, then creates it with `gh issue create`. Use when a finding, a request, an idea or a user story should become an issue; a description too vague for a goal or an observable acceptance comes back as a question instead of an item."
---

# Write an issue

## Input

A title and a description, however rough. An item is not a brief: it carries what must be true and how that is observed, and the brief `rules/brief.md` defines is written from it later.

## Shape

The body is these five headings, in this order, and nothing else:

```text
## Goal        one paragraph: what is true when the item is done
## Why         the evidence: file:line, probe output, the rule that is violated
## Proposal    the change, concrete enough to brief from
## Acceptance  one line per scenario, in the form `rules/brief.md` gives for Acceptance
## Related     one line per dependency, then the notes
```

A dependency is a line that begins `Depends on #N` after any list marker, several numbers allowed: `Depends on #4, #7`. Every other line in § Related is a note — out of scope, a sibling, background — and names items freely.

A `story` item keeps the five headings and changes two: § Goal is the three-part statement `As a <who>, I want <what>, so that <why>`, and each § Acceptance line is one Given/When/Then scenario — one line, one observable result, so the Acceptance form above holds. A story spanning several features is one item at `tier: complex`, or one `Depends on` line per feature issue it splits into. A description that opens `As a …`, and any request for a story, takes this shape and the `story` label beside `feature` or `enhancement`; one that reports a defect is a `bug` in the plain shape, without `story`.

## Labels

One from the type set, one priority, one tier, never two from one set; a type outside the set is refused.

- Type: `bug`; `feature`, one new capability; `enhancement`, a change to a capability that exists; `documentation`, docs alone.
- `story`, beside the type: the angle the item is written from, not a kind of its own (§ Shape).
- Priority: `priority: high`, `priority: medium` or `priority: low` — the tracker's own label descriptions decide which (`gh label list`).
- Tier: `tier: trivial`, `tier: standard` or `tier: complex`, per `skills/deliver/references/tiers.md`.
- Out of the queue, never written here: `question`, `duplicate`, `invalid`, `wontfix`.
- Topic and hint, no effect on the queue: `accessibility`, `good first issue`, `help wanted`.

## Refuse

When the Goal or Acceptance cannot be written from the description, create nothing and return one question under `## Questions` naming the missing sentence: the outcome that is not observable, or the input whose result is unstated.

One refusal per description. If the answer still leaves the same sentence missing, hand the description back as not actionable and stop.

## Create

1. The draft goes to the user first; creating an item is an external call, so it runs on their word (`rules/git.md`).
2. Write the body to the session scratchpad with the Write tool — never a shell heredoc.
3. `gh issue create --title <t> --label <type> --label <priority> --label <tier> --body-file <scratchpad file>`, with a further `--label story` when the item is one.

## Output

The item's number and its URL. Or the question, with nothing created.
