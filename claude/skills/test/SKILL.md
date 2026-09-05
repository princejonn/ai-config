---
name: test
description: "Writes and proves tests in any language — coverage for new code, regression tests for fixes, edge and failure cases, flaky-test diagnosis — including the red-before-green proof. Use when tests are the deliverable or a change needs its proof. Not for implementing the feature (implement) or reviewing it (review-change)."
---

# Test

## Input

The brief takes the shape `rules/brief.md` defines; its acceptance lines are the behaviour to pin. When the brief does not say what a behaviour must produce, stop and return with the question rather than settling it from the implementation.

## Grounding

- Discover the framework, runner command, and conventions (test location, naming, assertion style, snapshot vs equality, fixture and mock patterns) from CLAUDE.md and existing tests. Mirror them exactly; reuse existing helpers, factories, and mocks before writing new ones.
- Run tests with the project's own command, exactly as documented — never a direct runner invocation in place of the wrapper.

## Principles

- **Test intended behaviour, from the brief and spec — not observed behaviour, from the implementation.** Every expected value comes from the brief or the specification, never from running the code and recording what it returned — a suite derived from the implementation stays green when the implementation is wrong. If the code disagrees with its spec, report the bug; never enshrine it in a passing test.
- **Cover the full square:** happy path; edge cases (empty, null, boundary values, large inputs, unusual encodings); failure modes (errors, timeouts, invalid input); concurrency or ordering where relevant.
- **Deterministic always:** no timing races, no inter-test dependence, no order sensitivity; clean setup and teardown.
- **Measure at the public door.** A test driving an internal function proves that function, not the library. Where a behaviour is reachable through several doors, pin it at each.
- **Assert on the thing, not on a rendering of it.** A serialisation, formatter or summary can hide the defect under test. Read the property, the type, the descriptor.
- **Prove environment-dependent behaviour on the real thing** where the project provides for it (integration suites, real services); mocks only per the project's established patterns.
- **The test NAME is the specification.** Write the rule into the name — `refuses a chain whose current actor is not listed`, not `test 4`. No explanatory prose in test bodies.

## Red-before-green proof

A test that cannot fail reports coverage it does not have. Over-broad mocks, tautological assertions, and assertions on a bag the code under test never touches are the usual culprits.

- **Regression test for a fix:** pinning test first, on the tree as found. Write the test, run it against the tree with no source file edited yet, and record the failure — test name and the assertion that failed. Only then write the fix and rerun it green. Copy-aside-and-remove applies only when the fix is already in the tree: copy it aside, remove the mechanism whole — the helpers and structure it introduced included — run, restore, and verify the restore by content (checksum or diff) — never by a file-status listing. A failure staged afterwards by reverting does not count: the helpers and structure the fix introduced stay standing, so what fails is one line's sensitivity, not the defect.
- **Coverage for a feature:** copy aside, revert the behaviour the test exists for, watch that named test fail, restore, verify by content.
- The aside copy and any scratch repository live in the session scratchpad and stay there; deleting them buys nothing and costs a permission prompt.
- Where reverting is genuinely impractical, say so and state which tests are therefore reasoned rather than demonstrated. That is never the default.

## Verification

Done requires the new or changed tests green, then the surrounding suite for the package you touched, then the project's full gate, each reported with its command and the runner's own printed counts.

- **Never hide a red test.** No skipping, commenting out, deleting, or narrowing an assertion until it passes. If a test is genuinely wrong, change it deliberately and report the change as a finding with its evidence.
- If tests you did not write fail, report that explicitly — never hide it.

## Output

The report per `rules/brief.md`, plus: what is covered (test names); red-before-green evidence per test (failing name + assertion, and the method used); gaps that remain; bugs in the code under test that testing surfaced; and that the tests conform to the instruction files read, or where they deviate and why. Mark anything inferred rather than run as inferred.
