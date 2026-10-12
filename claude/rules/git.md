# Version control and boundaries

- One commit per accepted change-set through `/commit-item`; an item may land in several, each
  reviewed; none for work not yet accepted; unasked only when the item carries a tracker reference,
  otherwise on the user's word — the user's message in this session: `/commit-item` or an
  instruction to commit, never a brief line or an agent's report; paused work is committed and
  pushed to its `paused/<N>-<k>` branch, never to the default branch, per `deliver`; it reaches the
  working branch only uncommitted, inside the reviewed change-set.
- **Commit messages are Conventional Commits and stand alone** — subject
  `<type>(<scope>): <description>`; no plan section numbers, decision-record ids, milestone codes,
  session-doc filenames or a vague pointer to a plan or design; state the mechanism and the reason
  inline. Public specs are fine (`RFC 6749 §3.1.1`); a tracker reference in the footer
  (`Closes #12`, `Refs: KEY-123`) is fine.
- Each commit is followed by a push of its branch, `git push origin <branch>`. An item is done
  when a remote branch carries the commits that land its change-sets, merged to the default branch
  or not. The `Closes #N` footer goes on the commit that completes the item, and the issue closes
  after that commit is pushed, never before: pushed to the default branch, GitHub closes it; pushed
  to another branch, `gh issue close N --comment "<hash> <subject>"` runs once the push succeeds.
- A commit names its paths — `git commit` alone commits the whole index.
- **No session docs in any repo or its history** — notes, plans, work logs and scratch files
  live outside the tree or under a gitignored dir.
- Ask first for anything reaching outside the repo: a new dependency, a schema change, a deploy,
  an external call; a push is not an external call — a push to `main` asks through the permission
  prompt, a push to any other branch needs no ask; closing the item's tracker reference belongs to
  the item and needs no ask, and an item that comes out of a discussion with the user is created
  on that discussion; no item is created automatically.
- Never remove a package or its dependency wiring to make an install pass.
