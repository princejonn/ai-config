---
name: plan-phases
description: "Turns a design, feature request or refactor into a phased, verifiable execution plan — dependency ordering, blast radius, invariants and stop conditions per phase, migration and rollback, exit check per phase using the project's real commands. Use when an item touches an invariant, state boundary, security-sensitive code or several packages, before implement. Read-only."
---

# Plan

Read-only: this skill writes nothing but the plan.

## Input

The brief takes the shape `rules/brief.md` defines, and adds the design when there is one and the deliverable wanted — a phased plan.

## Grounding

- Plans are built from evidence: read the code being changed, grep for consumers and call sites, and derive the blast radius from what you find.
- Discover the project's real verification commands (build, test, lint, format, full gate) from CLAUDE.md, manifests, or CI config — every phase's exit check uses them.

## Method

1. **Map reality first.** What exists, who depends on it, what breaks if it changes. Cite files and call sites, not hunches.
2. **Phase the work.** Each phase is independently verifiable and leaves the tree green. Prefer more small phases over few large ones.
3. **Wide refactors** that no vertical slice keeps green run expand → migrate → contract: add the new form beside the old, move callers in batches that each leave the tree green, remove the old form last.
4. **Order by dependency and risk.** Front-load the riskiest unknowns so the plan fails fast; leave mechanical follow-through for late phases.
5. **Define verification per phase.** Name the exact command that proves the phase landed. A phase without an exit check is not a phase.
6. **State invariants and stop conditions.** Name what must hold tree-wide after each phase, and which assumption, if broken, means the developer stops and returns rather than works around.
7. **Name the unknowns.** Decisions needing user input, assumptions you could not verify, and external dependencies go in their own section — never buried inside a phase.
8. **Plan migration and rollback** whenever the work touches persisted data, published contracts, or live systems.

## Output

- **Goal and constraints** — in a few sentences.
- **Current code** — every claim about what exists today cites `file:line`. A claim without a citation is not made.
- **Phases** — for each: scope, files touched, dependencies on earlier phases, invariants, stop conditions, and the verification command.
- **Risks and unknowns** — with the question each one needs answered.
- **Deferred** — what is deliberately out of scope and why.
- The report per `rules/brief.md`.
