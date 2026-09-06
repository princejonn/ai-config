import json
import os
import subprocess
import sys
import unittest

HOOK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude", "hooks", "verdict-guard.py")
REVIEWER_FAILURE = "reviewer output must end with ACCEPTED, NOT ACCEPTED or BLOCKED\n"
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
    def test_accepted_as_the_final_line_lets_the_reviewer_stop(self):
        self.assertEqual(outcome(run(stop("reviewer", "Findings: none.\n\nACCEPTED"))), (0, "", ""))

    def test_not_accepted_as_the_final_line_lets_the_reviewer_stop(self):
        for message in ("Fixes:\n1. x\n\nNOT ACCEPTED", "Standards: NOT ACCEPTED\nSpec: NOT ACCEPTED\n\nNOT ACCEPTED"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_blocked_as_the_final_line_lets_the_reviewer_stop(self):
        message = "## Questions\n\nThe brief does not say whether 409 or 422 is expected. Which?\n\nBLOCKED"
        self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_emphasised_final_line_counts(self):
        for message in ("**ACCEPTED**", "Fixes:\n1. x\n\n**NOT ACCEPTED**", "__NOT ACCEPTED__", "`ACCEPTED`", "Which?\n\n**BLOCKED**"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_one_trailing_full_stop_on_the_final_line_counts(self):
        for message in ("ACCEPTED.", "Fixes:\n1. x\n\nNOT ACCEPTED.", "**ACCEPTED.**", "**ACCEPTED**.", "Which?\n\nBLOCKED."):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_blank_lines_after_the_verdict_still_count_it_as_final(self):
        for message in ("ACCEPTED\n", "ACCEPTED\n\n\n", "NOT ACCEPTED\n  \n\t\n"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (0, "", ""))

    def test_verdict_mentioned_in_prose_without_a_final_verdict_sends_the_reviewer_back(self):
        message = "The prior round was NOT ACCEPTED; no disposition this round."
        self.assertEqual(outcome(run(stop("reviewer", message))), (2, "", REVIEWER_FAILURE))

    def test_a_question_without_a_verdict_sends_the_reviewer_back(self):
        message = "## Questions\n\nThe brief does not say whether 409 or 422 is expected. Which?"
        self.assertEqual(outcome(run(stop("reviewer", message))), (2, "", REVIEWER_FAILURE))

    def test_prose_after_the_verdict_line_sends_the_reviewer_back(self):
        for message in ("ACCEPTED\n\nOne more note: rerun the gate.", "NOT ACCEPTED\nSee the fixes above."):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (2, "", REVIEWER_FAILURE))

    def test_final_line_that_is_not_the_token_alone_sends_the_reviewer_back(self):
        for message in ("Verdict: ACCEPTED", "Verdict: **ACCEPTED**.", "ACCEPTED, with one note", "(NOT ACCEPTED)", '"ACCEPTED"', "ACCEPTED.."):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (2, "", REVIEWER_FAILURE))

    def test_verdict_with_a_prefix_on_the_final_line_sends_the_reviewer_back(self):
        self.assertEqual(outcome(run(stop("reviewer", "Standards: NOT ACCEPTED\n\nVerdict: NOT ACCEPTED"))), (2, "", REVIEWER_FAILURE))

    def test_verdict_inside_another_word_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", "The change is UNACCEPTED."))), (2, "", REVIEWER_FAILURE))

    def test_lowercase_verdict_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", "accepted"))), (2, "", REVIEWER_FAILURE))

    def test_verifier_verdict_is_not_a_reviewer_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer", "VERIFIED"))), (2, "", REVIEWER_FAILURE))

    def test_missing_message_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("reviewer"))), (2, "", REVIEWER_FAILURE))

    def test_empty_or_blank_message_is_no_verdict(self):
        for message in ("", "\n\n", "  \n\t"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("reviewer", message))), (2, "", REVIEWER_FAILURE))

    def test_non_string_message_is_no_verdict(self):
        payload = json.loads(stop("reviewer"))
        payload["last_assistant_message"] = ["ACCEPTED"]
        self.assertEqual(outcome(run(json.dumps(payload))), (2, "", REVIEWER_FAILURE))


class VerifierVerdictTests(unittest.TestCase):
    def test_each_verdict_lets_the_verifier_stop(self):
        for token in ("VERIFIED", "DISPROVEN", "UNVERIFIABLE"):
            with self.subTest(token=token):
                self.assertEqual(outcome(run(stop("verifier", f"Claim 1: {token} — evidence at x:1."))), (0, "", ""))

    def test_ambiguous_claim_returns_unverifiable_with_the_readings(self):
        message = "Claim 1: UNVERIFIABLE — true under reading (a) `count` means rows, false under reading (b) `count` means bytes; the brief must pick one."
        self.assertEqual(outcome(run(stop("verifier", message))), (0, "", ""))

    def test_verdict_before_the_final_line_lets_the_verifier_stop(self):
        message = "Claim 1: VERIFIED.\nClaim 2: DISPROVEN.\n\nFalsification search: grep over src."
        self.assertEqual(outcome(run(stop("verifier", message))), (0, "", ""))

    def test_emphasised_verdict_counts(self):
        for message in ("Claim 1: **VERIFIED**", "Claim 1: __DISPROVEN__", "Claim 1: `UNVERIFIABLE`"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("verifier", message))), (0, "", ""))

    def test_verdict_with_surrounding_punctuation_counts(self):
        for message in ("Verdict: VERIFIED.", "(DISPROVEN)", '"VERIFIED"', "VERIFIED, with one note"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("verifier", message))), (0, "", ""))

    def test_verdict_inside_a_path_or_url_is_no_verdict(self):
        for message in ("see tests/VERIFIED.md", "https://example.com/VERIFIED for details", "x@VERIFIED", "VERIFIED-ish"):
            with self.subTest(message=message):
                self.assertEqual(outcome(run(stop("verifier", message))), (2, "", VERIFIER_FAILURE))

    def test_verdict_inside_another_word_is_no_verdict(self):
        self.assertEqual(outcome(run(stop("verifier", "Claim 1: UNVERIFIED."))), (2, "", VERIFIER_FAILURE))

    def test_no_verdict_sends_the_verifier_back(self):
        self.assertEqual(outcome(run(stop("verifier", "I read the file and it looks right."))), (2, "", VERIFIER_FAILURE))

    def test_reviewer_verdict_is_not_a_verifier_verdict(self):
        for token in ("ACCEPTED", "NOT ACCEPTED", "BLOCKED"):
            with self.subTest(token=token):
                self.assertEqual(outcome(run(stop("verifier", token))), (2, "", VERIFIER_FAILURE))


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
