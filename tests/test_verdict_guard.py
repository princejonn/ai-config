import json
import os
import subprocess
import sys
import unittest

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "verdict-guard.py")
REVIEWER_FAILURE = "reviewer output must end with ACCEPTED or NOT ACCEPTED\n"
VERIFIER_FAILURE = "verifier output must state VERIFIED, DISPROVEN or UNVERIFIABLE per claim\n"


def stop(agent_type, message=None, stop_hook_active=False):
    payload = {
        "hook_event_name": "SubagentStop",
        "session_id": "s1",
        "cwd": "/Users/jonn/Projects/x",
        "transcript_path": "/Users/jonn/.claude/projects/x/s1.jsonl",
        "agent_id": "a1",
        "agent_type": agent_type,
        "agent_transcript_path": "/Users/jonn/.claude/projects/x/a1.jsonl",
        "stop_hook_active": stop_hook_active,
    }
    if message is not None:
        payload["last_assistant_message"] = message
    return json.dumps(payload)


def run(stdin):
    return subprocess.run([sys.executable, HOOK_PATH], input=stdin, capture_output=True, text=True)


def outcome(proc):
    return proc.returncode, proc.stdout, proc.stderr


class ReviewerVerdictTests(unittest.TestCase):
    def test_accepted_lets_the_reviewer_stop(self):
        self.assertEqual(outcome(run(stop("reviewer", "Findings: none.\n\nACCEPTED"))), (0, "", ""))

    def test_not_accepted_lets_the_reviewer_stop(self):
        self.assertEqual(outcome(run(stop("reviewer", "Fixes:\n1. x\n\nNOT ACCEPTED"))), (0, "", ""))

    def test_emphasised_verdict_counts(self):
        for message in ("**ACCEPTED**", "__NOT ACCEPTED__", "`ACCEPTED`", "Verdict: **ACCEPTED**."):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_verdict_inside_another_word_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", "The change is UNACCEPTED."))), (2, "", REVIEWER_FAILURE))

    def test_verdict_inside_a_path_or_url_is_no_verdict(self):
        for message in ("see tests/ACCEPTED.md", "https://example.com/ACCEPTED for details", "x@ACCEPTED", "ACCEPTED-ish"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (2, "", REVIEWER_FAILURE))

    def test_verdict_with_surrounding_punctuation_counts(self):
        for message in ("Verdict: ACCEPTED.", "(NOT ACCEPTED)", '"ACCEPTED"', "ACCEPTED, with one note"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_lowercase_verdict_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", "accepted"))), (2, "", REVIEWER_FAILURE))

    def test_missing_message_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer"))), (2, "", REVIEWER_FAILURE))

    def test_empty_message_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", ""))), (2, "", REVIEWER_FAILURE))

    def test_non_string_message_is_no_verdict(self):
        payload = json.loads(stop("reviewer"))
        payload["last_assistant_message"] = ["ACCEPTED"]
        self.assertEqual(outcome(run(json.dumps(payload))), (2, "", REVIEWER_FAILURE))


class VerifierVerdictTests(unittest.TestCase):
    def test_each_verdict_lets_the_verifier_stop(self):
        for token in ("VERIFIED", "DISPROVEN", "UNVERIFIABLE"):
            with self.subTest(token=token):
                self.assertEqual(outcome(run(stop("verifier", f"Claim 1: {token} — evidence at x:1."))), (0, "", ""))

    def test_no_verdict_sends_the_verifier_back(self):
        self.assertEqual(outcome(run(stop("verifier", "I read the file and it looks right."))), (2, "", VERIFIER_FAILURE))

    def test_reviewer_verdict_is_not_a_verifier_verdict(self):
        self.assertEqual(outcome(run(stop("verifier", "ACCEPTED"))), (2, "", VERIFIER_FAILURE))


class FailOpenTests(unittest.TestCase):
    def test_unknown_agent_without_verdict_may_stop(self):
        self.assertEqual(outcome(run(stop("researcher", "Memo: three call sites."))), (0, "", ""))

    def test_missing_agent_type_may_stop(self):
        self.assertEqual(outcome(run(json.dumps({"hook_event_name": "SubagentStop", "stop_hook_active": False}))), (0, "", ""))

    def test_stop_hook_active_may_stop_without_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", "still no verdict", stop_hook_active=True))), (0, "", ""))

    def test_non_json_or_non_object_stdin_may_stop(self):
        for garbage in ("", "not json", "{{{", "[]", '"reviewer"'):
            with self.subTest(garbage=garbage):
                self.assertEqual(outcome(run(garbage)), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
