# Writing

- **The code carries the meaning; prose is a last resort.** A comment is a claim the reader must
  trust without checking, and trusted prose is where hallucination comes from. Spend the effort on
  a name, a type that makes the wrong state unwritable, or a test whose name states the rule. Write
  a comment only for a hazard a reasonable edit would break, and then one traced sentence.
- **A wrong comment is fixed by deleting it, never by rewriting it.**
- **No history in any repo.** GitHub carries the history; a repository carries only the present.
  Nothing in it — comment, docstring, type, test name, fixture, data table — records what the code
  used to do: no `used to`, `previously`, `no longer`, `legacy`, `renamed from`, no comment that
  something was removed, and no mechanism for it — no withdrawn-capabilities table, deprecation
  register or changelog constant. Why a change was made belongs in the commit body. Temporal words
  are not automatically history: the violation is a sentence whose only reason to exist is that
  something changed — grep finds candidates, reading decides. Backwards compatibility is discussed
  before it is implemented.
- **A specification reference is an address, not an argument.** A comment carries the bare, fully
  qualified reference — `RFC 9052 §5.2`, `OIDC Core §5.1.1` — and nothing more: never paraphrase,
  summarise or quote the section; never a bare `§x.y` — every citation names its document. The
  comment still ends at a checkable premise in the repo (a file, a function, a test name); "the RFC
  says so" is not one. Look the section up before changing what cites it; verify whole sentences,
  never fragments.
- Docs, READMEs, comments and commit messages are for a Nordic audience: short, concise, never
  verbose. Say it once and stop.

## Instruction files

- **An instruction file is a whole-file operation, never an append.** Fold a new rule into the one
  it refines, delete what it supersedes. A rule earns its place by changing what someone does,
  not by recording that something once happened; incidents go in the commit body.
- A rule that is really the answer fits in a sentence and generalises beyond the case that prompted it.
- What can be enforced mechanically is a hook, not prose. `~/.claude/hooks/` holds the global ones.
