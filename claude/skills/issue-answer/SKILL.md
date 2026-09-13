---
name: issue-answer
description: "Presents one open question from the tracker — the item's question with its recommendation — under ## Questions, records the user's ruling as a comment on the item and moves its label from question: open to question: closed. Use when asked which questions are open or waiting on the user, to answer or rule on a question filed on an issue, or to bring an item waiting on a ruling back into the queue. One at a time."
---

# Answer a question

## Input

One issue number, or none: then the first item carrying `question: open` in the list and order `issue-next` § Order gives, cited and not restated here. Each `gh` call here carries `--repo <owner/name>`, flag and value as separate words. `gh issue view <N> --json number,title,labels,comments --repo <owner/name>` reads the item; the latest comment opening `## Question` is the question, in the shape `issue-question` posts. The ruling leaves as the `Decisions made:` line `rules/brief.md` defines, which `issue-next` § Output reads.

An item under no `question: open`, or a tracker with none, is reported in one line and nothing is asked.

## Present

That one item's question, its options and its recommendation, under `## Questions` in the form `claude/CLAUDE.md` § Questions gives, then stop. One item per message: with several `question: open` items, one is presented and nothing else; the next waits for the next message.

## Rule

The user's reply is the ruling. A reply that does not rule — a question back, a request for more — posts nothing, and the item stays `question: open`.

1. The ruling, cleaned up to one or a few sentences that stand alone — no "yes", no option number, the decision in its own words — is written to the session scratchpad with the Write tool as `issue-<N>-ruling.md`, opening `## Ruling`, and posted with `gh issue comment <N> --body-file <scratchpad file> --repo <owner/name>`.
2. `gh issue edit <N> --remove-label "question: open" --add-label "question: closed" --repo <owner/name>`.
3. The reply names what restarts, from the question's `Filed from` line: `issue-triage` on the item for a question it filed, `issue-next` for one `deliver` filed — the item is back in the queue, its ruling under `Decisions made:`.

## Output

Before the ruling: the question, and nothing else. After it: one line — the item, the ruling's comment URL, the label it carries, and what restarts.
