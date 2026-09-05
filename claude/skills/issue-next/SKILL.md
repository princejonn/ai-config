---
name: issue-next
description: "Returns the next open item from the tracker as the fields a brief needs, ordered by urgency and blocked by nothing open. Use when asking what to work on next or which open issue is most urgent. Dispatches nothing."
---

# Next issue

## Input

None, or a repository: `--repo <owner/name>` then rides on every `gh` call below. The winner leaves as the fields `rules/brief.md` defines, so a brief is written from it without opening the tracker again.

## Order

`gh issue list --state open --limit 100 --json number,title,labels,body`, then sort:

1. Priority label: high, then medium, then low, then unlabelled.
2. Within a priority: bug before enhancement before neither.
3. Within that: the lowest number.

Two labels from one set: the item takes the more demanding one — the higher priority, `bug` over `enhancement`, the higher tier.

Walk the sorted list from the top and stop at the first item § Skip lets through. When every item is skipped, report the list and stop.

## Skip

- An item whose § Related carries a dependency line in the form `issue-write` § Shape gives: check each number it names with `gh issue view <N> --json state`. One still open skips the item, reported with the number that skipped it; a closed one does not block, and a note line is not a dependency. A number the view cannot resolve (exit 1, `Could not resolve`) does not block either: it is reported beside the winner as a malformed dependency line.
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

Then the items skipped above it, each with the open number that skipped it, and any malformed dependency line the winner carries. Nothing is dispatched here.
