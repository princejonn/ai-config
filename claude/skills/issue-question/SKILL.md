---
name: issue-question
description: "Files one question on one tracker item — the question, each option with an example and its cost, and one recommendation — as a comment, and labels the item question so it leaves the queue until the user rules. Use when a question on a named issue needs the user's word while other items continue, or when a triage fix list or a deviation from the agreed design is to be filed on its item; a question with no item is not filed here."
---

# File a question

## Input

One issue number and the question: nothing else names the subject. What filed it — `issue-triage` for a revise or question row, `deliver` for a deviation — rides along, since the ruling restarts there. `--repo <owner/name>` rides on every `gh` call here as two shell words. What leaves this skill is a comment whose ruling `issue-next` hands on as the `Decisions made:` field `rules/brief.md` defines.

## Method

1. A fix list from `issue-triage` § Critique, or the missing sentence of a question row, is filed as its own recommendation with no recommender run: the question is whether the item is revised as the list says. For every other question, `gh issue view <N> --json body,comments --repo <owner/name>` reads the item, and its state is its body and every comment, read as `issue-next` § Output reads them. The question goes to `recommender` as a brief in the shape `rules/brief.md` defines — the item's state, the question and the files it turns on — and comes back with one recommendation in the order `rules/decisions.md` gives and, per option, a concrete example and its cost; for an option that changes code or a file, the real text today and the real text proposed, each in a code block.
2. Each claim the recommendation rests on — a citation, a count, a "nothing else calls this" — goes through `/verify-claim`. One `DISPROVEN` verdict returns the question to the recommender once, the verdict attached; the second memo is filed whatever its verdicts, a verdict still `DISPROVEN` standing beside its claim in the comment.
3. One comment, written to the session scratchpad with the Write tool as `issue-<N>-question.md` and posted with `gh issue comment <N> --body-file <scratchpad file> --repo <owner/name>`:

   ```text
   ## Question
   <the question, one paragraph>

   ### Options
   <per option: a concrete example and its cost; for an option that changes code or a file, the real text today and the real text proposed, each in a code block>

   ### Recommendation
   <the one option, and the tie-break that decided it>

   Filed from: <issue-triage | deliver>
   ```

4. The label is `question`, with the description "An unanswered ## Question comment: out of the queue until its ## Ruling is posted". The tracker's labels, read with `gh label list --limit 1000 --json name --jq '.[].name' --repo <owner/name>` before the edit:
   - a `question` label there keeps its name and takes that description: `gh label edit question --description "<description>" --repo <owner/name>`.
   - none there, it is created: `gh label create question --description "<description>" --repo <owner/name>`.
   - then `gh issue edit <N> --add-label question --repo <owner/name>`, or `gh issue edit <N> --add-label question --remove-label ready --repo <owner/name>` when the list holds `ready`.

Done when the comment is posted and the item carries `question` and not `ready`: it is out of the queue per `issue-next` § Skip until `issue-answer` posts the ruling that leaves no question on it unanswered.

## Output

One line: the item, the labels it carries, the comment URL.
