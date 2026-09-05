---
name: research
description: "Runs one bounded research lane that enumerates — a repository survey for files, call sites, consumers and occurrences, or a web sweep for what exists — and returns a compact evidence memo with citations. Use when the orchestrator needs the findings without the page or file content landing in its context. Not for a lane that interprets what the sources mean (research-complex), checking one specific claim (verify) or reviewing code (review)."
context: fork
agent: researcher-trivial
---

# Research

## Input

The brief arrives as `$ARGUMENTS` in the shape `rules/brief.md` defines, and adds the question, the sources to sweep and what freshness matters.

## Sweep

1. Search and fetch broadly within the lane: web queries from several phrasings, the suggested sources, and the primary sources behind them (official docs, changelogs, issue trackers, specifications, papers). For local lanes, locate and skim the relevant files; for specifications, prefer the local copies the project's CLAUDE.md names.
2. **Open what you cite.** Never cite a source you did not fetch; prefer primary sources over aggregators.
3. Stay inside the lane. If the trail leads somewhere material but out of scope, record it as a lead instead of following it.

The sweep is done when the sources the brief names are exhausted and further queries return only sources already read.

## Memo

The memo is compact, structured, and complete enough to be used without re-fetching:

- **Findings**: each with its evidence — URL or file path, plus the load-bearing quote or datum. State publication or last-updated dates where freshness matters.
- **Contradictions**: sources that disagree, stated side by side; never silently pick one.
- **Confidence**: well-sourced vs thinly sourced vs could not be confirmed.
- **Leads**: material out-of-scope trails worth a follow-up lane.

Never return raw page content wholesale, and never present an unverified claim as established.
