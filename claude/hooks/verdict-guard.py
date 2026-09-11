#!/usr/bin/env python3
"""SubagentStop hook: a reviewer whose last message does not end with ACCEPTED, NOT ACCEPTED or BLOCKED, or a verifier whose last message states none of VERIFIED, DISPROVEN, UNVERIFIABLE, is sent back to give a verdict."""

import json
import re
import sys

EMPHASIS = re.compile(r"[*_`]")
BEFORE = r'(?:^|(?<=[\s("]))'
AFTER = r'(?=$|[\s.,;:!?)"])'


def ends_with_verdict(message, tokens):
    lines = [line for line in message.splitlines() if line.strip()]
    if not lines:
        return False
    final = EMPHASIS.sub("", lines[-1]).strip()
    return any(final in (token, token + ".") for token in tokens)


def states_verdict(message, tokens):
    plain = EMPHASIS.sub("", message)
    return any(re.search(BEFORE + re.escape(token) + AFTER, plain, re.MULTILINE) for token in tokens)


REVIEWER = (("ACCEPTED", "NOT ACCEPTED", "BLOCKED"), ends_with_verdict, "reviewer output must end with ACCEPTED, NOT ACCEPTED or BLOCKED")

VERDICTS = {
    "reviewer": REVIEWER,
    "reviewer-complex": REVIEWER,
    "verifier": (("VERIFIED", "DISPROVEN", "UNVERIFIABLE"), states_verdict, "verifier output must state VERIFIED, DISPROVEN or UNVERIFIABLE per claim"),
}


def evaluate(hook_input):
    """Returns the message the agent is sent back with, or None when it may stop."""
    if not isinstance(hook_input, dict) or hook_input.get("stop_hook_active"):
        return None
    verdict = VERDICTS.get(hook_input.get("agent_type"))
    if verdict is None:
        return None
    tokens, states, failure = verdict
    message = hook_input.get("last_assistant_message")
    if isinstance(message, str) and states(message, tokens):
        return None
    return failure


def main():
    try:
        failure = evaluate(json.loads(sys.stdin.read()))
    except Exception:
        sys.exit(0)
    if failure is None:
        sys.exit(0)
    print(failure, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
