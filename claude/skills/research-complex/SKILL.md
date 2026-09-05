---
name: research-complex
description: "Runs one bounded research lane that interprets — what a specification section requires, what a dependency behaviour actually is, which reading a corpus supports — and returns a compact evidence memo with citations. Use when a design or a verdict will rest on the answer. Not for a lane that enumerates files, call sites or occurrences (research), checking one specific claim (verify) or reviewing code (review)."
context: fork
agent: researcher-complex
---

# Research (interpreting)

## Input

The brief arrives as `$ARGUMENTS` in the shape `rules/brief.md` defines, and adds the question whose answer a design or a verdict will rest on, and where to start.

## Method

The procedure is `skills/research/SKILL.md` § Sweep and § Memo; this lane differs in the model that runs it, not in what it does.

## Done

The memo per the research skill's output contract.
