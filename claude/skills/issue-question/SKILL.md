---
name: issue-question
description: "Files one question on one tracker item — the question, each option with an example and its cost, and one recommendation — as a comment, and labels the item question: open so it leaves the queue until the user rules. Use when a question on a named issue needs the user's word while other items continue, or when a triage fix list or a deviation from the agreed design is to be filed on its item; a question with no item is not filed here."
---

# File a question

## Input

One issue number and the question: nothing else names the subject. What filed it — `issue-triage` for a revise or question row, `deliver` for a deviation — rides along, since the ruling restarts there. `--repo <owner/name>` rides on every `gh` call here as two shell words. What leaves this skill is a comment whose ruling `issue-next` hands on as the `Decisions made:` field `rules/brief.md` defines.

## Method

1. A fix list from `issue-triage` § Critique, or the missing sentence of a question row, is filed as its own recommendation with no recommender run: the question is whether the item is revised as the list says. Every other question goes to `recommender` as a brief in the shape `rules/brief.md` defines — the item's body, the question and the files it turns on — and comes back as each option with one concrete input/output example and its cost, and one recommendation in the order `rules/decisions.md` gives.
2. Each claim the recommendation rests on — a citation, a count, a "nothing else calls this" — goes through `/verify-claim`. One `DISPROVEN` verdict returns the question to the recommender once, the verdict attached; the second memo is filed whatever its verdicts, a verdict still `DISPROVEN` standing beside its claim in the comment.
3. One comment, written to the session scratchpad with the Write tool as `issue-<N>-question.md` and posted with `gh issue comment <N> --body-file <scratchpad file> --repo <owner/name>`:

   ```text
   ## Question
   <the question, one paragraph>

   ### Options
   <one per option: what happens, a concrete input and its output, the cost>

   ### Recommendation
   <the one option, and the tie-break that decided it>

   Filed from: <issue-triage | deliver>
   ```

4. The labels, read with `gh label list --limit 1000 --json name --jq '.[].name' --repo <owner/name>` before the edit:
   - a bare label named question, with neither `question: open` nor `question: closed` present, is renamed: `gh label edit question --name "question: open" --repo <owner/name>`; beside either new label it is left, and § Output says so.
   - a label still absent is created: `gh label create "question: open" --repo <owner/name>`, `gh label create "question: closed" --repo <owner/name>`.
   - then `gh issue edit <N> --add-label "question: open" --remove-label "question: closed" --repo <owner/name>`.

Done when the comment is posted and the item carries `question: open`: it is out of the queue per `issue-next` § Skip until `issue-answer` closes the question.

## Output

One line: the item, the label it carries, the comment URL — and the bare label left in place, when one was.
