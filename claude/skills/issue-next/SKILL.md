---
name: issue-next
description: "Returns the next open item from the tracker as the fields a brief needs, ordered `priority: blocker` first, then by status, then urgency, and blocked by nothing open. Use when asking what to work on next or which open issue is most urgent."
---

# Next issue

## Input

None, or a repository: `--repo <owner/name>` then rides on every `gh issue` call below, and its owner and name fill the read in § Skip. The winner leaves as the fields `rules/brief.md` defines, so a brief is written from it without opening the tracker again.

## Order

`gh issue list --state open --limit 1000 --json number,title,labels,body`, then sort by the vocabulary `skills/issue-write/SKILL.md` § Labels defines:

1. Priority label: blocker, then high, then medium, then low, then unlabelled.
2. Within a priority, type label: bug, feature, enhancement, documentation, then no type.
3. Within that: the lowest number.

Two labels from one set: the item takes the more demanding one — the higher priority, the earlier type in bug, feature, enhancement, documentation, the higher tier.

A `story` label changes no position: the item orders by its type.

The sorted list then splits into four groups, each keeping its order: the items carrying `priority: blocker`, whatever their status, then of the rest the items carrying `paused`, then those carrying `ready`, then the backlog, which carries neither. Walk the groups in turn and stop at the first item § Skip lets through. When every item is held, report the list and stop.

## Skip

- The holds are the labels `question`, `parked`, `blocked`, `invalid` and `wontfix`, and an open blocker or piece below; a held item is out of the queue whatever its status. A hold label skips the item, reported with the label that skipped it, before any dependency is checked.
- One read per candidate gives its blockers and its pieces: `gh api graphql -f query='query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issue(number:<N>){blockedBy(first:50){nodes{number state}} subIssues(first:50){nodes{number state}}}}}' -F owner=<owner> -F name=<name>`. An open node under `blockedBy` skips the item, reported with the number that skipped it; an open node under `subIssues` skips it the same way, a split parent closing against its pieces. A number named by a dependency line in § Related, in the form `issue-write` § Shape gives, that neither `blockedBy` nor `subIssues` carries is reported beside the winner as a malformed dependency line.
- The item that survives, read as § Output reads it, when it carries no § Acceptance section: return `BLOCKED` with the sentence `issue-write` would need — the scenario and the exact result it must produce — and stop. The item is repaired before anything is dispatched.

## Output

The winner as brief fields, filled from the item and nothing else. `gh issue view <N> --json body,comments` reads it as an event log: the body is the starting state, and each comment applies in order, a later one overriding what it names in the body or an earlier comment. A `## Brief`, `## Plan` or `## Design` comment overrides nothing: it is evidence the item carries, read as itself. Every field carries the state after the last comment.

A `ready` or `paused` winner leaves as its latest `## Brief` comment, in the shape `issue-triage` § Ready posts it, with each `## Ruling` posted after that comment added under `Decisions made:`. One with no `## Brief` leaves as a backlog winner does. A backlog winner leaves as these fields, derived from the state:

```text
Item:            #N and its URL
Goal:            one sentence from § Goal, or the title with a note when the item has none
Acceptance:      § Acceptance verbatim, one line per scenario
Decisions made:  the rulings on the item, one per line, or none
Tier:            the tier label, or standard with a note that the item carries none
Out of scope:    what § Related says the item does not cover, or none
```

`Decisions made:` is every comment that opens `## Ruling`, the shape `issue-answer` posts, in comment order, or `none`.

Then the items skipped above it, each with the open number or the label that skipped it, and any malformed dependency line the winner carries. A backlog winner leaves flagged as one to triage, not to deliver. Nothing is dispatched here.
