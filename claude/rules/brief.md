# Brief

A brief carries everything the agent needs cold, in this shape:

```text
Goal:            <one sentence>
Item:            <tracker reference — #N, KEY-123, a URL — or "none">
Acceptance:      <scenario → exact observable result>, one per line
Files in scope:  <absolute paths>
Decisions made:  <settled; not relitigated>
Verification:    <the project's exact command(s)>
Invariant:       <tree-wide, for a fix; "none" otherwise>
Instructions:    <absolute paths of the AGENTS.md / CLAUDE.md that apply>
Tier:            <trivial | standard | complex>
Out of scope:    <explicit>
```

A detail omitted is a decision not made: the writer leaves none open, the reader fills none. A blocking omission returns as a question; a non-blocking one is listed under "Unclear in the brief" in the agent's report.

## Report

The agent's report carries, whatever else the skill adds: Files changed; Verification — the command and the runner's own summary line, or "none run"; Instructions read — the paths; Unclear in the brief; Left open — what the brief asked for and is not delivered. Report only what was done: never an action not performed or a result not measured; anything inferred rather than run is marked inferred.
