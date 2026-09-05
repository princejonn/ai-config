---
name: root-cause
description: "Finds the root cause of a defect before any fix — a reproducer first, ranked falsifiable hypotheses, one variable at a time — and hands the pinning test to the fix. Use when asked to debug, when behaviour is wrong and the cause is not yet known, and again when a fix has failed twice. Not for implementing the fix (implement) or proving tests (test)."
---

# Debug

## Rule

No fix without a root cause shown by a reproducer. A fix that makes the symptom go away without a named mechanism is a guess, and a guess that passes is the most expensive kind.

## Reproduce

- Build the tightest pass/fail signal first: one command that fails now.
- Minimise the input until one change flips it.
- If it cannot be reproduced, say so and stop; nothing is fixed blind.

## Hypothesise

- List three to five candidate mechanisms, each with the observation that would falsify it.
- Rank by how cheap that observation is, not by how likely the mechanism feels.

## Instrument

- Change one variable at a time.
- Read the actual output from a file, never a summary of it.
- A hypothesis survives only its falsification test; a surviving one is stated as `file:line` plus mechanism.

## Stop rule

After two failed fixes, return to Reproduce: the model of the system is wrong, not the fix.

## Hand-off

- The reproducer becomes the pinning test (see the test skill's red-before-green proof).
- The cause goes into the brief for implement.
- Instrumentation is removed before hand-off.

## Output

- Cause as `file:line` and mechanism.
- The reproducer command.
- Hypotheses falsified and by what.
- The pinning test name.
