---
name: author-gherkin
description: "Writes Gherkin `.feature` files for a package's public surfaces: one Feature per surface, one scenario per public behaviour, steps in the domain's words. Use when a brief asks for a feature file, a scenario or Gherkin, or names a `.feature` path. Not for a deterministic unit test (test) or for implementing the code under test (implement)."
---

# Author a feature file

## Input

The brief takes the shape `rules/brief.md` defines, and names the package and the public surface to describe. The skill reads that surface's exported classes and functions and takes the behaviours from them. A brief naming no surface returns as a question.

## Scenario shape

- One `Feature:` per public surface.
- `Background:` for the setup every scenario shares; `Rule:` to group.
- `Example:` or `Scenario:` for one behaviour — one behaviour per scenario.
- `Scenario Outline:` with an `Examples:` table when one dimension varies; each column is an input or a result the scenario text names.
- `Given`, `When` and `Then` in the domain's words: no class, method, file or type name in a step.
- No tags unless the brief names them.

## Placement

The file sits beside the surface it describes, following the package's existing `.feature` placement: `Widget.ts`, `Widget.feature` and `Widget.test.ts` in one directory.

## Coverage

Every exported public method or function of the named surface carries at least one scenario, error paths included. Done when each one is either covered or listed as uncovered in the report; a behaviour is never silently dropped.

## Run

The package's own test command executes the features; the skill runs it when the brief asks for a run, and otherwise leaves it to the package. The skill writes no step definitions, configures nothing, and says nothing about which runner a package uses.

## Output

- The files written.
- Per surface, the scenarios written and the behaviours left without one.
- The runner's own summary line verbatim when the package's test command was run. Undefined steps are the expected result for a feature whose steps do not exist yet: quote the line, never suppress or work around it.
