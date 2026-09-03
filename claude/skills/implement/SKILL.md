---
name: implement
description: "Implements one defined code change in any language — feature, refactor, bug fix, scaffolding — to production quality: complete work, tests via the test skill with red-before-green proof, the project's full gate green, and a report of what changed with verification evidence. Use for any code change, inline or in the developer agent; when the brief carries a plan, its stop conditions bind. Not for tests as the deliverable (test) or design (design)."
---

# Implement

## Input

A brief carries: the goal; acceptance criteria as concrete observable values, never prose ("refused with 409, not queued"); the files in scope; decisions already made (settled, not relitigated); the project's verification command; and, for a fix, the invariant the fix must hold tree-wide. Add no restriction, validation, contract, or capability beyond what the brief, the repository's instruction files, or the language and its libraries require.

When the brief carries a plan, its stop conditions bind: a broken plan assumption means stop and return with what you found, never an improvised workaround. A complex-tier brief without a plan is a blocking omission.

## Grounding

- Use the project's exact commands (build, test, lint, format, full gate) from CLAUDE.md, manifests, or CI config — never a generic substitute for the project's wrapper.
- Read the files you are changing and their neighbours first. Match what you find — naming, idiom, error handling, file layout.
- **Verify the premise you were handed.** A brief, plan, report or docstring describing the code is a claim, not evidence. Check the load-bearing ones against the source before building on them, and say plainly when one is wrong — a real symptom with a wrong cause produces a fix that papers over it.

## Method

Explore → implement → verify. No shortcuts:

- **Complete work only.** Production-grade, thoroughly tested. No stubs, no leftover TODOs, no half-handled cases. Handle errors explicitly and keep existing contracts intact. If the task uncovers a deeper problem, fix it properly or report it explicitly — never paper over it.
- **Changes carry tests** unless the brief says otherwise: happy path, edge cases, failure modes, in the project's test conventions, asserting intended behaviour. A change without tests is unfinished. Expected values come from the brief or the specification as `test` § Principles directs; where the brief does not give the value, that is an omission: report it, do not settle it from your code.
- **Every test is proved red-before-green** as `test` § Red-before-green proof describes — pinning test first for a fix, revert-and-restore for a feature.
- **Hold every invariant the brief or plan names across the whole tree it governs**, not just at the reported site. Spend your reasoning on the failure modes the plan flags as tricky — correctness first, speed nowhere.
- **Fit the codebase:** its patterns, naming, idiom and comment density.
- **Never dismiss a failing check as "pre-existing".** If it fails in your verification path, fix it or report it as an explicit blocker with the output.
- **In monorepos**, rebuild changed dependency packages before running dependents' checks, per the project's build ordering.
- **Stay scoped.** Do the task; report adjacent problems rather than silently expanding the diff.
- **When you change behaviour, re-read the prose around it.** Prose true before your change and false after is the commonest defect of this class.
- **When you correct a rule, grep for its other copies** — comments, test names, fixture/spec text.
- **A count or list in prose carries the command that produced it.**

## Boundaries

- Never add a dependency, commit, or push unless the brief instructs it.
- Never edit vendored or generated directories, secrets, or version fields owned by release tooling.

## Verification

Run the narrowest relevant check first, then the project's full gate for everything you touched — tests, typecheck, build, lint and format. "Done" requires a passing check — include the commands and the runners' printed counts as evidence; never a partial landing.

- A type-level change needs the project's typecheck specifically — a build or test pass may exclude test sources.
- If you cannot get green, say exactly what fails and why instead of claiming success.

## Output

Report:

- What changed (files and why) and any adjacent problem noticed and left alone.
- Verification evidence: commands and the runner's printed counts.
- Red-before-green evidence per test: the failing test name and assertion, with the fix-first or revert-after method used.
- Omissions in the brief you noticed and did not fill; any stop condition tripped and what you found.
- **Compliance:** which instruction files apply (by path) and that the change conforms, or exactly where it deviates and why.

**Report only what you actually did.** Never describe an action you did not perform or a result you did not measure; mark anything inferred rather than run as inferred.
