import importlib.util
import json
import os
import subprocess
import sys
import unittest

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "dispatch-guard.py")
SPEC = importlib.util.spec_from_file_location("dispatch_guard", HOOK_PATH)
dispatch_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dispatch_guard)

ALIASES = ("sonnet", "opus", "fable")
MODEL_AT_DISPATCH = ("developer", "researcher", "reviewer")
BUILT_IN = ("general-purpose", "Explore", "Plan")
NO_MODEL_RULE = "dispatch-guard.py: a `{agent}` spawn without `model` runs its frontmatter pin, not the model chosen at dispatch."
FABLE_ONLY_RULE = "dispatch-guard.py: `recommender` always runs on `fable`; this spawn passes `model: {model}`."
FABLE_ONLY_PERMITTED = "the same spawn bare."


def spawn(subagent_type=None, **parameters):
    tool_input = {"description": "one task", "prompt": "Goal: one task"}
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    tool_input.update(parameters)
    return {"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/Users/someone/Projects/x", "tool_name": "Agent", "tool_input": tool_input}


def evaluate(subagent_type=None, **parameters):
    return dispatch_guard.evaluate(spawn(subagent_type, **parameters))


def decision(result):
    return None if result is None else result["hookSpecificOutput"]["permissionDecision"]


def reason(result):
    return result["hookSpecificOutput"]["permissionDecisionReason"]


def rule(result):
    return reason(result).split(" Permitted: ", 1)[0]


def run(stdin):
    return subprocess.run([sys.executable, HOOK_PATH], input=stdin, capture_output=True, text=True)


def outcome(proc):
    return proc.returncode, proc.stdout, proc.stderr


class ModelAtDispatchTests(unittest.TestCase):
    def test_each_of_developer_researcher_and_reviewer_without_model_is_denied(self):
        for agent in MODEL_AT_DISPATCH:
            with self.subTest(agent=agent):
                result = evaluate(agent)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(rule(result), NO_MODEL_RULE.format(agent=agent))

    def test_developer_researcher_and_reviewer_with_each_alias_are_permitted(self):
        for agent in MODEL_AT_DISPATCH:
            for alias in ALIASES:
                with self.subTest(agent=agent, model=alias):
                    self.assertIsNone(evaluate(agent, model=alias))


class FableOnlyTests(unittest.TestCase):
    def test_a_recommender_spawn_with_a_model_other_than_fable_is_denied_with_a_reason_naming_fable(self):
        for model in ("sonnet", "opus"):
            with self.subTest(model=model):
                result = evaluate("recommender", model=model)
                self.assertEqual(decision(result), "deny")
                self.assertEqual(reason(result), f"{FABLE_ONLY_RULE.format(model=model)} Permitted: {FABLE_ONLY_PERMITTED}")

    def test_a_bare_recommender_spawn_is_permitted(self):
        self.assertIsNone(evaluate("recommender"))
        for model in (None, ""):
            with self.subTest(model=model):
                self.assertIsNone(evaluate("recommender", model=model))


class UnguardedSpawnTests(unittest.TestCase):
    def test_a_built_in_agent_type_without_model_is_permitted(self):
        for agent in BUILT_IN:
            with self.subTest(agent=agent):
                self.assertIsNone(evaluate(agent))


class MainTests(unittest.TestCase):
    def test_a_denial_prints_a_pre_tool_use_deny_decision_naming_the_hook_and_exits_0(self):
        proc = run(json.dumps(spawn("developer")))
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        output = json.loads(lines[0])["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertTrue(output["permissionDecisionReason"].startswith("dispatch-guard.py: "), output["permissionDecisionReason"])

    def test_non_json_non_object_or_missing_tool_input_stdin_is_silent_and_exits_0(self):
        for garbage in ("", "not json", "{{{", "[]", '"developer"', '{"tool_name": "Agent"}', '{"tool_name": "Agent", "tool_input": "developer"}'):
            with self.subTest(stdin=garbage):
                self.assertEqual(outcome(run(garbage)), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
