---
paths: ["**/*.ts", "**/*.tsx"]
---

# Code style

Defaults for code the user owns; in someone else's repo its established idiom wins.

- **Initialisms first-letter-only** — `Uri`, `Url`, `Id`, `Jwk`; `tokenUri`, `keyId`, `baseUrl`. No
  exceptions. Both sides of an option spell it the same; never a `baseURL: baseUrl` mapping. Outside
  the rule: third-party type keys (axios `baseURL`), Node globals (`new URL()`), SCREAMING_SNAKE.
- **`Array<T>`, never `T[]`** — including `Array<keyof X>`, never `(keyof X)[]`.
- **Never negate a comparison predicate — use its opposite.** `isAfter` for `!isBefore`; an
  `isExpired` / `isLive` predicate for expiry. `!isBefore(a,b)` is `a >= b`, `isAfter(a,b)` is
  `a > b`: state which boundary a predicate means and test it.
- **Never `Object.assign`** — a wrong property attaches silently. Assign by name or build a typed literal.
- **No runtime `typeof x === "…"`** — use the project's type-guard library; if the guard is missing,
  add it there with its test. Type-level `typeof`, and `instanceof` where a `Symbol.for` brand is not
  the idiom, are fine.
- **Throw at the site.** Construct and throw inline where the failure is detected — no error factories,
  no helpers whose job is to throw. A helper may return a decision; the caller throws.
- **Guard style: positive check, early return.** A helper with one happy condition tests it with `===`
  and returns; the throw is the unindented tail. Multi-check asserts keep one `if (bad) throw` per check.
- **Expression-bodied arrows.** A body that is one `return` is an expression body (parenthesise an object
  literal). Block bodies only for guards, multiple statements or early returns — no ternary contortions.
- **No dead code lands.** TypeScript never flags an unused export, orphan file or unused dep: before a
  commit, grep `src/` for importers of each new export and classify — dead → delete; not-yet-consumed
  public API → keep; ambiguous → report, don't touch.

## Anchors a root supplies

Two rules take their answer from the root: the type-guard library behind "No runtime `typeof`", and
the expiry predicates behind "Never negate a comparison predicate". The root's `CLAUDE.md` names both
under the heading "Anchors for code-style.md".
