---
name: issue-answer
description: "Presents one open question from the tracker — the item's question with its recommendation — under ## Questions, records the user's ruling as a comment on the item, removes its question label once no question on it is left unanswered, and sets ready when the ruling is ready on the ready question. Use when asked which questions are open or waiting on the user, to answer or rule on a question filed on an issue, to rule an item ready, or to bring an item waiting on a ruling back into the queue. One at a time."
---

# Answer a question

## Input

One issue number, or none: then the first item `gh issue list --state open --limit 1000 --label question --json number,title,labels,comments --repo <owner/name>` lists with a `## Question` still unanswered, in the order `issue-next` § Order gives, cited and not restated here. Each `gh` call here carries `--repo <owner/name>`, flag and value as separate words. `gh issue view <N> --json number,title,labels,comments --repo <owner/name>` reads a named item. A `## Ruling` comment answers the earliest unanswered `## Question` before it, and the question is the earliest `## Question` still unanswered, in the shape `issue-question` posts. The ruling leaves as the `Decisions made:` line `rules/brief.md` defines, which `issue-next` § Output reads.

An item under no `question`, one whose every `## Question` is answered, or a tracker with no item under `question` is reported in one line, and nothing is asked. The items the pick passes over are named in that same one line, and the pick goes on.

## Present

That one item's question and its recommendation, under `## Questions` in the form `claude/CLAUDE.md` § Questions gives — the one line or the full one, as the question calls for — then stop. One item per message: with several `question` items, one is presented and nothing else; the next waits for the next message.

## Rule

The user's reply is the ruling. A reply that does not rule — a question back, a request for more — posts nothing, and the item keeps `question`.

1. The ruling, cleaned up to one or a few sentences that stand alone — no "yes", no option number, the decision in its own words — is written to the session scratchpad with the Write tool as `issue-<N>-ruling.md`, opening `## Ruling`, and posted with `gh issue comment <N> --body-file <scratchpad file> --repo <owner/name>`.
2. With no `## Question` on the item left unanswered, `gh issue edit <N> --remove-label question --repo <owner/name>` — and when the question is the ready question `issue-triage` § Ready files and the ruling is ready, `gh issue edit <N> --add-label ready --remove-label question --repo <owner/name>` instead, `ready` unless the item carries `paused`, which keeps the first call. With any left, the item keeps `question`, and the earliest of them is the next one presented.
3. Once `question` is off, the reply names what restarts, from the `Filed from` line of the question just ruled: nothing for the ready question `issue-triage` § Ready files when the ruling is ready — the item is `ready`, and `issue-next` hands it on; `issue-triage` on the item for every other ruling on a question `issue-triage` filed, for one `issue-write` filed and for one `deliver § Intake` filed; `issue-next` for one `deliver` filed — the item is back in the queue, its rulings under `Decisions made:`.

## Output

Before the ruling: § Input's one line when the pick passed over an item, then the question, and nothing else. After it: one line — the item, the ruling's comment URL, the labels it carries, and what restarts, if anything does.
