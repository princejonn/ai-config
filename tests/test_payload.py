import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAUDE = REPO / "claude"
SKILLS = CLAUDE / "skills"
AGENTS = CLAUDE / "agents"
RULES = CLAUDE / "rules"
HOOKS = CLAUDE / "hooks"

SKILL_NAME = re.compile(r"^[a-z0-9-]{1,64}$")
DESCRIPTION_MAX = 1024
BODY_MAX_LINES = 200
CLAUDE_MD_MAX_BYTES = 3400
MODELS = {"fable", "sonnet"}

SKILL_FIELDS_BEYOND_NAME_AND_DESCRIPTION = {
    "research": {"context": "fork", "agent": "researcher"},
    "verify": {"context": "fork", "agent": "verifier"},
    "review": {"context": "fork", "agent": "reviewer"},
    "commit": {"disable-model-invocation": True},
    "design": {},
    "plan": {},
    "implement": {},
    "test": {},
    "deliver": {},
}
AGENT_KEYS = {"name", "description", "color", "model", "effort", "tools"}
EXPECTED_AGENT_SKILLS = {"developer": ["implement", "test"], "tester": ["test"]}
EXPECTED_AGENTS = {"developer", "researcher", "reviewer", "tester", "verifier"}

ONE_HOME_PHRASES = (
    "never pipe through",
    "enumerating the population",
    "copy it aside",
)
ABSENT_PHRASES = (
    "exhaustive over intent",
    "The tree is not yours",
    "returned to the orchestrator verbatim",
)

MEANING_CHANGE_EXAMPLES = "or the meaning of one (what an operator does, which boundary a predicate uses, whether a value counts as absent)"
EXPECTED_VALUES_RATIONALE = "a suite derived from the implementation stays green when the implementation is wrong"
PINNING_TEST_FIRST = "Write the test, run it against the tree with no source file edited yet, and record the failure — test name and the assertion that failed. Only then write the fix and rerun it green."
COPY_ASIDE_ONLY_WHEN_FIX_PRESENT = "only when the fix is already in the tree"
STAGED_FAILURE_WARNING = "A failure staged afterwards by reverting does not count: the helpers and structure the fix introduced stay standing, so what fails is one line's sensitivity, not the defect."
CORRECTNESS_FIRST = "Spend your reasoning on the failure modes the plan flags as tricky — correctness first, speed nowhere."


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


def payload_files():
    return [CLAUDE / "CLAUDE.md", *rule_files(), *(d / "SKILL.md" for d in skill_dirs()), *agent_files()]


def skill_docs():
    return {d.name: parse_frontmatter(read(d / "SKILL.md")) for d in skill_dirs()}


def agent_docs():
    return {p.stem: parse_frontmatter(read(p)) for p in agent_files()}


def section(body, heading):
    start = body.index(f"\n## {heading}\n")
    end = body.find("\n## ", start + 1)
    return body[start:] if end == -1 else body[start:end]


class FrontmatterParserTest(unittest.TestCase):
    def test_flat_forms(self):
        fields, body = parse_frontmatter('---\na: "x: y"\nb: bare words, with comma\nc: true\nd: false\ne: [one, two]\nf: []\n---\n\nbody\n')
        self.assertEqual(fields, {"a": "x: y", "b": "bare words, with comma", "c": True, "d": False, "e": ["one", "two"], "f": []})
        self.assertEqual(body, "\nbody\n")

    def test_no_frontmatter_returns_none(self):
        fields, body = parse_frontmatter("# Heading\n")
        self.assertIsNone(fields)
        self.assertEqual(body, "# Heading\n")

    def test_duplicate_key_raises(self):
        with self.assertRaises(ValueError):
            parse_frontmatter("---\na: one\na: two\n---\n")

    def test_indented_line_raises(self):
        with self.assertRaises(ValueError):
            parse_frontmatter("---\na:\n  b: nested\n---\n")

    def test_unbalanced_quote_raises(self):
        with self.assertRaises(ValueError):
            parse_frontmatter('---\na: "open\n---\n')
        with self.assertRaises(ValueError):
            parse_frontmatter("---\na: close'\n---\n")
        with self.assertRaises(ValueError):
            parse_frontmatter('---\na: [one, "two]\n---\n')


class SkillsTest(unittest.TestCase):
    def test_skill_set_is_exactly_the_nine(self):
        self.assertEqual({d.name for d in skill_dirs()}, set(SKILL_FIELDS_BEYOND_NAME_AND_DESCRIPTION))
        for d in skill_dirs():
            self.assertTrue(d.is_dir(), d)
            self.assertTrue((d / "SKILL.md").is_file(), d)

    def test_name_matches_dir_and_pattern(self):
        for name, (fields, _) in skill_docs().items():
            with self.subTest(skill=name):
                self.assertEqual(fields["name"], name)
                self.assertRegex(name, SKILL_NAME)
                self.assertNotIn("claude", name)
                self.assertNotIn("anthropic", name)

    def test_description_shape(self):
        for name, (fields, _) in skill_docs().items():
            with self.subTest(skill=name):
                assert_description(self, fields["description"])

    def test_body_at_most_200_lines(self):
        for name, (_, body) in skill_docs().items():
            with self.subTest(skill=name):
                self.assertLessEqual(len(body.splitlines()), BODY_MAX_LINES)

    def test_frontmatter_matches_expected_table(self):
        for name, (fields, _) in skill_docs().items():
            with self.subTest(skill=name):
                expected = SKILL_FIELDS_BEYOND_NAME_AND_DESCRIPTION[name]
                self.assertEqual(set(fields), {"name", "description", *expected})
                self.assertEqual({key: fields[key] for key in expected}, expected)


class AgentsTest(unittest.TestCase):
    def test_agent_set_is_exactly_the_five(self):
        for p in agent_files():
            self.assertEqual(p.suffix, ".md", p)
        self.assertEqual({p.stem for p in agent_files()}, EXPECTED_AGENTS)

    def test_frontmatter_matches_expected_table(self):
        for stem, (fields, _) in agent_docs().items():
            with self.subTest(agent=stem):
                expected_keys = AGENT_KEYS | ({"skills"} if stem in EXPECTED_AGENT_SKILLS else set())
                self.assertEqual(set(fields), expected_keys)
                self.assertEqual(fields["name"], stem)
                self.assertIn(fields["model"], MODELS)
                self.assertTrue(fields["tools"])
                assert_description(self, fields["description"])
                if stem in EXPECTED_AGENT_SKILLS:
                    self.assertEqual(fields["skills"], EXPECTED_AGENT_SKILLS[stem])

    def test_developer_effort_is_xhigh(self):
        fields, _ = agent_docs()["developer"]
        self.assertEqual(fields["effort"], "xhigh")


class RulesTest(unittest.TestCase):
    def test_code_style_is_scoped_to_typescript(self):
        fields, _ = parse_frontmatter(read(RULES / "code-style.md"))
        self.assertIn("**/*.ts", fields["paths"])

    def test_other_rules_have_no_frontmatter(self):
        for p in rule_files():
            if p.name == "code-style.md":
                continue
            with self.subTest(rule=p.name):
                fields, _ = parse_frontmatter(read(p))
                self.assertIsNone(fields)


class HooksTest(unittest.TestCase):
    def test_every_manifest_script_exists(self):
        manifest = json.loads(read(CLAUDE / "hooks.json"))
        for event, entries in manifest.items():
            for entry in entries:
                with self.subTest(event=event, script=entry["script"]):
                    self.assertTrue((HOOKS / entry["script"]).is_file())


class ClaudeMdTest(unittest.TestCase):
    def test_at_most_3400_bytes(self):
        self.assertLessEqual((CLAUDE / "CLAUDE.md").stat().st_size, CLAUDE_MD_MAX_BYTES)


class OneHomeTest(unittest.TestCase):
    def test_each_one_home_phrase_occurs_exactly_once_across_payload(self):
        for phrase in ONE_HOME_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertEqual(sum(phrase_homes(phrase).values()), 1, phrase_homes(phrase))

    def test_each_absent_phrase_occurs_nowhere_in_payload(self):
        for phrase in ABSENT_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertEqual(phrase_homes(phrase), {})


class SkillPassagesTest(unittest.TestCase):
    def test_design_description_names_the_meaning_change_examples(self):
        fields, _ = skill_docs()["design"]
        self.assertIn(MEANING_CHANGE_EXAMPLES, fields["description"])

    def test_test_principles_say_why_expected_values_come_from_the_spec(self):
        _, body = skill_docs()["test"]
        principles = section(body, "Principles")
        self.assertIn("Every expected value comes from the brief or the specification", principles)
        self.assertIn(EXPECTED_VALUES_RATIONALE, principles)
        self.assertLess(principles.index("Every expected value comes from"), principles.index(EXPECTED_VALUES_RATIONALE))

    def test_test_fix_proof_orders_pinning_test_then_copy_aside_then_staged_failure_warning(self):
        _, body = skill_docs()["test"]
        proof = section(body, "Red-before-green proof")
        for passage in (PINNING_TEST_FIRST, COPY_ASIDE_ONLY_WHEN_FIX_PRESENT, STAGED_FAILURE_WARNING):
            self.assertIn(passage, proof)
        self.assertLess(proof.index(PINNING_TEST_FIRST), proof.index(COPY_ASIDE_ONLY_WHEN_FIX_PRESENT))
        self.assertLess(proof.index(COPY_ASIDE_ONLY_WHEN_FIX_PRESENT), proof.index(STAGED_FAILURE_WARNING))

    def test_implement_method_puts_correctness_before_speed(self):
        _, body = skill_docs()["implement"]
        self.assertIn(CORRECTNESS_FIRST, section(body, "Method"))


def phrase_homes(phrase):
    return {str(p.relative_to(REPO)): read(p).count(phrase) for p in payload_files() if phrase in read(p)}


def assert_description(case, description):
    case.assertTrue(description)
    case.assertLessEqual(len(description), DESCRIPTION_MAX)
    for prefix in ("I ", "You ", "Use this"):
        case.assertFalse(description.startswith(prefix), description)


if __name__ == "__main__":
    unittest.main()
