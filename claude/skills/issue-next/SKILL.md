---
name: issue-next
description: "Returns the next open item from the tracker as the fields a brief needs, ordered by urgency and blocked by nothing open. Use when asking what to work on next or which open issue is most urgent. Dispatches nothing."
---

# Next issue

## Input

None, or a repository: `--repo <owner/name>` then rides on every `gh issue` call below, and its owner and name fill the read in § Skip. The winner leaves as the fields `rules/brief.md` defines, so a brief is written from it without opening the tracker again.

## Order

`gh issue list --state open --limit 100 --json number,title,labels,body`, then sort by the vocabulary `skills/issue-write/SKILL.md` § Labels defines:

1. Priority label: high, then medium, then low, then unlabelled.
2. Within a priority, type label: bug, feature, enhancement, documentation, then no type.
3. Within that: the lowest number.

Two labels from one set: the item takes the more demanding one — the higher priority, the earlier type in bug, feature, enhancement, documentation, the higher tier.

A `story` label changes no position: the item orders by its type.

Walk the sorted list from the top and stop at the first item § Skip lets through. When every item is skipped, report the list and stop.

## Skip

- An open item carrying `parked`, `blocked`, `question`, `duplicate`, `invalid` or `wontfix` is out of the queue: skipped and reported with the label that skipped it, before any dependency is checked.
- One read per candidate gives its blockers and its pieces: `gh api graphql -f query='query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issue(number:<N>){blockedBy(first:50){nodes{number state}} subIssues(first:50){nodes{number state}}}}}' -F owner=<owner> -F name=<name>`. An open node under `blockedBy` skips the item, reported with the number that skipped it; an open node under `subIssues` skips it the same way, a split parent closing against its pieces. A number named by a dependency line in § Related, in the form `issue-write` § Shape gives, that neither `blockedBy` nor `subIssues` carries is reported beside the winner as a malformed dependency line.
- The item that survives, when it carries no § Acceptance section: return `BLOCKED` with the sentence `issue-write` would need — the scenario and the exact result it must produce — and stop. The item is repaired before anything is dispatched.

## Output

The winner as brief fields, filled from the item and nothing else:

```text
Item:          #N and its URL
Goal:          one sentence from § Goal, or the title with a note when the item has none
Acceptance:    § Acceptance verbatim, one line per scenario
Tier:          the tier label, or standard with a note that the item carries none
Out of scope:  what § Related says the item does not cover, or none
```

Then the items skipped above it, each with the open number or the label that skipped it, and any malformed dependency line the winner carries. Nothing is dispatched here.
