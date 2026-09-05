---
name: verify-claim
description: "Checks one load-bearing claim, or a small coupled set, before it is ratified into a design, plan or review verdict or relayed to the user as fact — 'nothing else calls this', 'the RFC requires X', 'the dependency is at version Y', 'all N sites were fixed', a bug diagnosis, a TODO premise. Returns VERIFIED, DISPROVEN or UNVERIFIABLE with falsification-grade evidence. Not for reviewing a change-set (review-change) or broad source gathering (research)."
context: fork
agent: verifier
---

# Verify

## Input

The brief arrives as `$ARGUMENTS` in the shape `rules/brief.md` defines, and adds each claim verbatim, its role (what decision rests on it) and where to start looking. When the claim is true under one reading and false under another, the verdict is `UNVERIFIABLE` and the missing artefact is the choice between the readings — list them.

## What counts as a claim

A claimed bug — from Claude, an agent, a consumer report or a TODO entry — and a dismissed one get the same treatment: the diagnosis in `file:line` terms, the fix proved red-before-green. A TODO premise is not evidence; re-derive from HEAD and correct the entry.

## Method

1. **Try to falsify the claim, not to confirm it.** Locate the authoritative artefact — the repository code, the installed dependency source, command output, a version-matched primary document — and read what it actually does. Prefer a safe empirical check (run it, observe it) over inference from source when behaviour is the question.
2. Counterexamples to a quantified claim hide in overrides, other writers, other callers, dynamic dispatch, string-keyed registration and config-declared entry points: run the targeted search that would surface them.
3. **Track versions.** A claim about a dependency is verified against the version the repository actually uses — manifest, lockfile, installed tree — never against generic documentation or recall.
4. **A claim citing a specification is verified in the primary text.** Read the cited section itself (the project's CLAUDE.md names where local copies live) and check whole sentences, never fragments — a real prefix welded to an invented tail reads exactly like a quote.
5. Stay on the claim. Material discoveries outside it are leads in your verdict, not scope.

## Verdict

One verdict per claim — **VERIFIED**, **DISPROVEN**, or **UNVERIFIABLE** — plus:

- **Evidence**: `file:line` of the source read, the command run with its relevant output, or the version-matched document and section — precise enough to re-check without redoing the work.
- **Falsification search**: what you looked for that would have disproven the claim, and where you looked.
- For **DISPROVEN**: what is actually true, at the same grade of evidence.
- For **UNVERIFIABLE**: exactly which artefact or access was missing.
- **Leads**: material out-of-scope discoveries.

"Plausible", "likely", and unlabelled inference are not verdicts.
