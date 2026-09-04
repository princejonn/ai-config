#!/usr/bin/env python3
"""SubagentStop hook: a reviewer or verifier whose last message states no verdict is sent back to state one."""

import json
import re
import sys

VERDICTS = {
    "reviewer": (("ACCEPTED", "NOT ACCEPTED"), "reviewer output must end with ACCEPTED or NOT ACCEPTED"),
    "verifier": (("VERIFIED", "DISPROVEN", "UNVERIFIABLE"), "verifier output must state VERIFIED, DISPROVEN or UNVERIFIABLE per claim"),
}
EMPHASIS = re.compile(r"[*_`]")
BEFORE = r'(?:^|(?<=[\s("]))'
AFTER = r'(?=$|[\s.,;:!?)"])'


def states_verdict(message, tokens):
    plain = EMPHASIS.sub("", message)
    return any(re.search(BEFORE + re.escape(token) + AFTER, plain, re.MULTILINE) for token in tokens)


def evaluate(hook_input):
    """Returns the message the agent is sent back with, or None when it may stop."""
    if not isinstance(hook_input, dict) or hook_input.get("stop_hook_active"):
        return None
    verdict = VERDICTS.get(hook_input.get("agent_type"))
    if verdict is None:
        return None
    tokens, failure = verdict
    message = hook_input.get("last_assistant_message")
    if isinstance(message, str) and states_verdict(message, tokens):
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
