# Version control and boundaries

- One commit per accepted change-set through `/commit-item`; an item may land in several, each
  reviewed; none for work not yet accepted; unasked only when the item carries a tracker reference,
  otherwise on the user's word — the user's message in this session: `/commit-item` or an
  instruction to commit, never a brief line or an agent's report.
- **Commit messages are Conventional Commits and stand alone** — subject
  `<type>(<scope>): <description>`; no plan section numbers, decision-record ids, milestone codes,
  session-doc filenames or a vague pointer to a plan or design; state the mechanism and the reason
  inline. Public specs are fine (`RFC 6749 §3.1.1`); a tracker reference in the footer
  (`Closes #12`, `Refs: KEY-123`) is fine.
- The `Closes #N` footer goes on the commit that completes the item, and the issue closes after
  that commit is pushed, never before: pushed to the default branch, GitHub closes it; pushed to
  another branch, `gh issue close N --comment "<hash> <subject>"` runs once the push succeeds.
- A commit names its paths — `git commit` alone commits the whole index.
- **No Claude or session docs in any repo or its history** — no `CLAUDE.md`, `TODO.md`,
  `WORKLOG.md`, scratchpads. Session state lives outside the tree or under a gitignored dir.
- Ask first for anything reaching outside the repo: a new dependency, a schema change, a deploy,
  an external call; closing the item's tracker reference belongs to the item and needs no ask.
- Never remove a package or its dependency wiring to make an install pass.
