# Version control and boundaries

- Commit only when the user asks, through `/commit`.
- **Commit messages are Conventional Commits and stand alone** — subject
  `<type>(<scope>): <description>`; no plan section numbers, decision-record ids, milestone codes,
  session-doc filenames or a vague pointer to a plan or design; state the mechanism and the reason
  inline. Public specs are fine (`RFC 6749 §3.1.1`).
- A commit names its paths — `git commit` alone commits the whole index.
- **No Claude or session docs in any repo or its history** — no `CLAUDE.md`, `TODO.md`,
  `WORKLOG.md`, scratchpads. Session state lives outside the tree or under a gitignored dir.
- Ask first for anything reaching outside the repo: a new dependency, a schema change, a deploy,
  an external call.
- Never remove a package or its dependency wiring to make an install pass.
