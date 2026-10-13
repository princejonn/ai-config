#!/usr/bin/env python3
"""PreToolUse hook (Agent): a developer, researcher or reviewer spawn without `model` is denied, and so is a recommender spawn whose `model` is not `fable`."""

import json
import sys

HOOK = "dispatch-guard.py"
MODEL_AT_DISPATCH = ("developer", "researcher", "reviewer")
FABLE_ONLY = "recommender"


def deny(rule: str, permitted: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{HOOK}: {rule} Permitted: {permitted}",
        }
    }


def passed_model(tool_input: dict) -> str | None:
    model = tool_input.get("model")
    return model if isinstance(model, str) and model else None


def evaluate(hook_input: object) -> dict | None:
    tool_input = hook_input["tool_input"]
    agent = tool_input.get("subagent_type")
    model = passed_model(tool_input)
    if agent in MODEL_AT_DISPATCH and model is None:
        return deny(
            f"a `{agent}` spawn without `model` runs its frontmatter pin, not the model chosen at dispatch.",
            "the same spawn with `model:` as the precedence in `skills/deliver/references/tiers.md` picks.",
        )
    if agent == FABLE_ONLY and model is not None and model != "fable":
        return deny(f"`{FABLE_ONLY}` always runs on `fable`; this spawn passes `model: {model}`.", "the same spawn bare.")
    return None


def main() -> None:
    try:
        result = evaluate(json.loads(sys.stdin.read()))
        if result is not None:
            print(json.dumps(result))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
