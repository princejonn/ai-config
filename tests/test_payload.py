import importlib.util
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE = REPO / "claude"
SKILLS = CLAUDE / "skills"
AGENTS = CLAUDE / "agents"
RULES = CLAUDE / "rules"
RULESETS = CLAUDE / "rulesets"
HOOKS = CLAUDE / "hooks"
MANIFEST = CLAUDE / "settings.json"

SPEC = importlib.util.spec_from_file_location("verdict_guard", HOOKS / "verdict-guard.py")
verdict_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verdict_guard)
DISPATCH_SPEC = importlib.util.spec_from_file_location("dispatch_guard", HOOKS / "dispatch-guard.py")
dispatch_guard = importlib.util.module_from_spec(DISPATCH_SPEC)
DISPATCH_SPEC.loader.exec_module(dispatch_guard)

SKILL_NAME = re.compile(r"^[a-z0-9-]{1,64}$")
RESERVED_SKILL_NAMES = {
    "verify",
    "debug",
    "design",
    "plan",
    "review",
    "commit",
    "code-review",
    "artifact-components",
    "batch",
    "claude-api",
    "claude-in-chrome",
    "design-sync",
    "plan-artifact",
    "pr",
    "run",
    "run-skill-generator",
    "simplify",
    "update-config",
}
DESCRIPTION_MAX = 1024
CLAUDE_MD_MAX_BYTES = 8600
MODELS = {"fable", "opus", "sonnet"}
COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
AGENT_KEYS = {"name", "description", "color", "model", "effort", "tools"}
RECOMMENDER_TOOLS = "Read, Grep, Glob, WebFetch, WebSearch"
OPEN_PULL_REQUEST_OPENAI_POLICY = "policy:\n  allow_implicit_invocation: false\n"


def parse_value(raw):
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [parse_value(item.strip()) for item in inner.split(",")] if inner else []
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw[:1] in ("\"", "'") or raw[-1:] in ("\"", "'"):
        raise ValueError(f"unbalanced quote: {raw!r}")
    if raw == "true":
        return True
    if raw == "false":
        return False
    return raw


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    fields = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if line[0].isspace():
            raise ValueError(f"nested value: {line!r}")
        key, sep, raw = line.partition(":")
        if not sep:
            raise ValueError(f"not a key: value line: {line!r}")
        if key.strip() in fields:
            raise ValueError(f"duplicate key: {key.strip()!r}")
        fields[key.strip()] = parse_value(raw.strip())
    return fields, text[end + len("\n---\n"):]


def read(path):
    return path.read_text(encoding="utf-8")


def skill_dirs():
    return sorted(p for p in SKILLS.iterdir() if p.name != ".DS_Store")


def agent_files():
    return sorted(p for p in AGENTS.iterdir() if p.name != ".DS_Store")


def rule_files():
    return sorted(p for p in RULES.iterdir() if p.name != ".DS_Store")


def ruleset_files():
    return sorted(RULESETS.glob("*/*.md"))


def skill_docs():
    return {d.name: parse_frontmatter(read(d / "SKILL.md")) for d in skill_dirs()}


def agent_docs():
    return {p.stem: parse_frontmatter(read(p)) for p in agent_files()}


class SkillsTest(unittest.TestCase):
    def test_no_skill_takes_a_name_claude_code_reserves(self):
        self.assertEqual({d.name for d in skill_dirs()} & RESERVED_SKILL_NAMES, set())

    def test_name_matches_dir_and_pattern(self):
        for name, (fields, _) in skill_docs().items():
            with self.subTest(skill=name):
                self.assertEqual(fields["name"], name)
                self.assertRegex(name, SKILL_NAME)
                self.assertNotIn("claude", name)
                self.assertNotIn("anthropic", name)

    def test_description_is_present_and_at_most_1024_characters(self):
        for name, (fields, _) in skill_docs().items():
            with self.subTest(skill=name):
                assert_description(self, fields["description"])


class AgentsTest(unittest.TestCase):
    def test_frontmatter_keys_and_values_are_valid_and_every_preloaded_skill_exists(self):
        skills = {d.name for d in skill_dirs()}
        for stem, (fields, _) in agent_docs().items():
            with self.subTest(agent=stem):
                self.assertEqual(set(fields) - {"skills"}, AGENT_KEYS)
                self.assertEqual(fields["name"], stem)
                self.assertIn(fields["model"], MODELS)
                self.assertIn(fields["color"], COLORS)
                self.assertIn(fields["effort"], EFFORTS)
                self.assertTrue(fields["tools"])
                assert_description(self, fields["description"])
                self.assertLessEqual(set(fields.get("skills", [])), skills)

    def test_recommender_is_read_only_on_fable_at_xhigh_effort(self):
        fields, _ = agent_docs()["recommender"]
        self.assertEqual(fields["tools"], RECOMMENDER_TOOLS)
        self.assertEqual(fields["model"], "fable")
        self.assertEqual(fields["effort"], "xhigh")


class RulesTest(unittest.TestCase):
    def test_every_global_rule_has_no_frontmatter(self):
        for p in rule_files():
            with self.subTest(rule=p.name):
                fields, _ = parse_frontmatter(read(p))
                self.assertIsNone(fields)

    def test_every_ruleset_rule_lists_at_least_one_paths_glob(self):
        for p in ruleset_files():
            with self.subTest(rule=p.relative_to(RULESETS).as_posix()):
                fields, _ = parse_frontmatter(read(p))
                self.assertIsNotNone(fields)
                paths = fields.get("paths")
                self.assertIsInstance(paths, list)
                self.assertTrue(paths)
                for pattern in paths:
                    self.assertIsInstance(pattern, str)
                    self.assertTrue(pattern)


class HooksTest(unittest.TestCase):
    def test_every_manifest_script_exists(self):
        manifest = json.loads(read(MANIFEST))
        for event, entries in manifest["hooks"].items():
            for entry in entries:
                with self.subTest(event=event, script=entry["script"]):
                    self.assertTrue((HOOKS / entry["script"]).is_file())

    def test_subagent_stop_matcher_names_exactly_the_agents_verdict_guard_judges(self):
        manifest = json.loads(read(MANIFEST))
        entry = next(e for e in manifest["hooks"]["SubagentStop"] if e["script"] == "verdict-guard.py")
        self.assertEqual(set(entry["matcher"].split("|")), set(verdict_guard.VERDICTS))

    def test_dispatch_guard_runs_on_every_agent_call(self):
        manifest = json.loads(read(MANIFEST))
        entries = [e for e in manifest["hooks"]["PreToolUse"] if e["script"] == "dispatch-guard.py"]
        self.assertEqual([e["matcher"] for e in entries], ["Agent"])

    def test_dispatch_guard_judges_only_agents_the_tree_defines(self):
        judged = {*dispatch_guard.MODEL_AT_DISPATCH, dispatch_guard.FABLE_ONLY}
        self.assertLessEqual(judged, {p.stem for p in agent_files()})


class ClaudeMdTest(unittest.TestCase):
    def test_at_most_8600_bytes(self):
        self.assertLessEqual((CLAUDE / "CLAUDE.md").stat().st_size, CLAUDE_MD_MAX_BYTES)

    def test_routing_table_names_every_skill_once(self):
        body = (CLAUDE / "CLAUDE.md").read_text(encoding="utf-8")
        for skill in skill_dirs():
            with self.subTest(skill=skill.name):
                self.assertEqual(body.count(f"| `{skill.name}` |"), 1)


class OpenPullRequestTest(unittest.TestCase):
    def test_open_pull_request_ships_an_openai_yaml_whose_policy_disallows_implicit_invocation(self):
        path = SKILLS / "open-pull-request" / "agents" / "openai.yaml"
        self.assertTrue(path.is_file(), path)
        self.assertEqual(read(path), OPEN_PULL_REQUEST_OPENAI_POLICY)


def assert_description(case, description):
    case.assertTrue(description)
    case.assertLessEqual(len(description), DESCRIPTION_MAX)


if __name__ == "__main__":
    unittest.main()
