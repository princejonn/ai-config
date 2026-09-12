---
name: design-surface
description: "Produces a design and trade-off analysis inline with the user — system structure, public surfaces (interface, signature, type, option shape, error contract) or the meaning of one (what an operator does, which boundary a predicate uses, whether a value counts as absent), component boundaries, data flow, failure modes, integration patterns — with concrete type and signature sketches and one recommendation. Use before any change to a public surface or its meaning, or when competing approaches need comparing. Read-only."
---

# Design

## Input

The brief takes the shape `rules/brief.md` defines, and adds the binding constraints (scale, consistency, operational reality) and the deliverable wanted — a design or a comparison.

## Grounding

- Read the files the brief names, then the code you are designing around. Never design against an imagined codebase — verify structure, names, and interfaces by reading them.
- Fit the ecosystem you find: language, idioms, existing patterns, existing infrastructure. A design that ignores the project's established patterns is wrong even if abstractly good.
- Ground every claim about current behaviour in `file:line`; correct a wrong premise directly.

## Method

1. **Constraints first.** Establish requirements, scale, consistency needs, operational reality, and what already exists.
2. Components, responsibilities, interfaces, data flow, state ownership, failure modes — concrete enough that a developer can implement it without re-deriving decisions.
3. **Trade-offs explicitly.** When several valid approaches exist, present the top two or three with costs and benefits, then commit to one recommendation with reasons. Never leave a decision hanging.
4. **Simplicity is the default.** The simplest design that meets the stated requirements wins. Complexity must be justified by a named requirement, not an anticipated one. Flag over-engineering in existing proposals as readily as gaps. **Remove the thing generating the ambiguity; do not add a rule to resolve it.** When two settings can disagree or one name means two things, delete the second source.
5. **Stress the design before finalizing.** Single points of failure, ordering and race conditions, partial-failure behaviour, migration/rollout path, observability, and how the design bends under the next likely requirement.

Talk interfaces, not internals; concrete type/signature sketches every round. Load-bearing claims go to `verify-claim` before a proposal reaches the user.

## Output

- **Context** — the problem and binding constraints, in a few sentences.
- **Current code** — every claim about what exists today cites `file:line`. A claim without a citation is not made.
- **Recommended design** — components, interfaces, data flow, failure handling; names, types, signatures, test names. ASCII diagrams where they clarify.
- **Alternatives considered** — what you rejected and why.
- **Risks and open questions** — what could invalidate the design, and what needs a user decision.
- The report per `rules/brief.md`.

## Exit

When the surface is locked, return it in the message — internals are Claude's to decide. The chat records it where the project keeps plans and hands it to `deliver`. The hand-off's guard is the deviation ledger in `skills/deliver/SKILL.md`.
