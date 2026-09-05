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

SKILL_NAME = re.compile(r"^[a-z0-9-]{1,64}$")
DESCRIPTION_MAX = 1024
BODY_MAX_LINES = 200
CLAUDE_MD_MAX_BYTES = 8600
MODELS = {"fable", "opus", "sonnet"}
COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}

SKILL_FIELDS_BEYOND_NAME_AND_DESCRIPTION = {
    "research": {"context": "fork", "agent": "researcher-trivial"},
    "research-complex": {"context": "fork", "agent": "researcher-complex"},
    "verify": {"context": "fork", "agent": "verifier"},
    "review": {"context": "fork", "agent": "reviewer"},
    "commit": {},
    "design": {},
    "plan": {},
    "implement": {},
    "test": {},
    "deliver": {},
    "debug": {},
    "second-opinion": {},
    "author-skill": {},
    "issue-write": {},
    "issue-next": {},
    "issue-triage": {},
}
SKILLS_WITH_INPUT = {"design", "implement", "issue-next", "issue-triage", "issue-write", "plan", "research", "research-complex", "review", "test", "verify"}
AGENT_KEYS = {"name", "description", "color", "model", "effort", "tools"}
DEVELOPER_MODELS = {"developer-trivial": ("sonnet", "high"), "developer-standard": ("opus", "xhigh"), "developer-complex": ("fable", "xhigh")}
RESEARCHER_MODELS = {"researcher-trivial": ("sonnet", "high"), "researcher-complex": ("fable", "high")}
EXPECTED_AGENT_SKILLS = {**{name: ["implement", "test", "debug"] for name in DEVELOPER_MODELS}, "tester": ["test"]}
EXPECTED_AGENTS = {"developer-trivial", "developer-standard", "developer-complex", "researcher-trivial", "researcher-complex", "reviewer", "tester", "verifier"}
FORK_ONLY_AGENTS = {"researcher-trivial", "researcher-complex", "reviewer", "verifier"}
RESEARCH_PROCEDURE_HEADINGS = ("## Sweep", "## Memo")

ONE_HOME_PHRASES = {
    "never pipe through": "claude/CLAUDE.md",
    "three tool calls": "claude/CLAUDE.md",
    "enumerating the population": "claude/CLAUDE.md",
    "a decision not made": "claude/rules/brief.md",
    "Unclear in the brief": "claude/rules/brief.md",
    "copy it aside": "claude/skills/test/SKILL.md",
    "root cause": "claude/skills/debug/SKILL.md",
    "decorrelation": "claude/skills/second-opinion/SKILL.md",
    "the brief is incomplete and the question is above": "claude/skills/review/SKILL.md",
    "it is not a round": "claude/skills/deliver/SKILL.md",
    "tier of the code it touches": "claude/skills/deliver/references/tiers.md",
    "unique output": "claude/skills/deliver/references/review-loop.md",
    "reviewed baseline": "claude/skills/deliver/references/review-loop.md",
    "fix delta plus the": "claude/skills/review/SKILL.md",
    "wearing a review's clothes": "claude/skills/deliver/references/review-loop.md",
    "needs no ask": "claude/rules/git.md",
    "never a brief line": "claude/rules/git.md",
    "Goal or Acceptance cannot be written": "claude/skills/issue-write/SKILL.md",
    "Depends on #N": "claude/skills/issue-write/SKILL.md",
    "have to be weighed for": "claude/skills/deliver/references/tiers.md",
    "bug, feature, enhancement, documentation": "claude/skills/issue-next/SKILL.md",
    "As a <who>, I want <what>, so that <why>": "claude/skills/issue-write/SKILL.md",
    "edits nothing before the ruling": "claude/skills/issue-triage/SKILL.md",
    "carries no orchestration": "claude/skills/author-skill/SKILL.md",
}
ABSENT_PHRASES = (
    "@lindorm",
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
BRIEF_FIELD_LABELS = ("Goal:", "Item:", "Acceptance:", "Files in scope:", "Decisions made:", "Verification:", "Invariant:", "Instructions:", "Tier:", "Out of scope:")
ISSUE_BODY_HEADINGS = ("## Goal", "## Why", "## Proposal", "## Acceptance", "## Related")
REPOSITORY_LABELS = (
    "bug",
    "feature",
    "enhancement",
    "documentation",
    "story",
    "priority: high",
    "priority: medium",
    "priority: low",
    "tier: trivial",
    "tier: standard",
    "tier: complex",
    "blocked",
    "question",
    "duplicate",
    "invalid",
    "wontfix",
    "accessibility",
    "good first issue",
    "help wanted",
)
OUT_OF_QUEUE_LABELS = ("blocked", "question", "duplicate", "invalid", "wontfix")
ISSUE_NEXT_BRIEF_FIELDS = ("Item:", "Goal:", "Acceptance:", "Tier:", "Out of scope:")
ISSUE_TRIAGE_SECTIONS = ("Input", "State", "Draft", "Duplicate", "Critique", "Done", "Apply", "Output")
ISSUE_TRIAGE_DISPATCH_WORDS = (r"lanes?", r"fork(s|ed|ing)?", r"parallel")


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


def reference_files():
    return sorted(SKILLS.glob("*/references/*.md"))


def payload_files():
    return [CLAUDE / "CLAUDE.md", *rule_files(), *ruleset_files(), *(d / "SKILL.md" for d in skill_dirs()), *reference_files(), *agent_files()]


def skill_docs():
    return {d.name: parse_frontmatter(read(d / "SKILL.md")) for d in skill_dirs()}


def agent_docs():
    return {p.stem: parse_frontmatter(read(p)) for p in agent_files()}


def section(body, heading):
    start = body.index(f"\n## {heading}\n")
    end = body.find("\n## ", start + 1)
    return body[start:] if end == -1 else body[start:end]


def sentence_count(text):
    return len(re.findall(r'[.!?]["\u201d)]*(?=\s|$)', text.strip()))


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
    def test_skill_set_is_exactly_the_expected_table(self):
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
    def test_agent_set_is_exactly_the_expected_table(self):
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
                self.assertIn(fields["color"], COLORS)
                self.assertIn(fields["effort"], EFFORTS)
                self.assertTrue(fields["tools"])
                assert_description(self, fields["description"])
                if stem in EXPECTED_AGENT_SKILLS:
                    self.assertEqual(fields["skills"], EXPECTED_AGENT_SKILLS[stem])

    def test_fork_only_agent_description_is_one_sentence_under_200_characters(self):
        docs = agent_docs()
        for stem in FORK_ONLY_AGENTS:
            with self.subTest(agent=stem):
                description = docs[stem][0]["description"]
                self.assertLess(len(description), 200)
                self.assertEqual(sentence_count(description), 1)

    def test_every_agent_body_is_exactly_two_sentences(self):
        for stem, (_, body) in agent_docs().items():
            with self.subTest(agent=stem):
                self.assertEqual(sentence_count(body), 2)

    def test_each_developer_pins_its_tier_model_and_effort(self):
        docs = agent_docs()
        for stem, (model, effort) in DEVELOPER_MODELS.items():
            with self.subTest(agent=stem):
                fields, _ = docs[stem]
                self.assertEqual((fields["model"], fields["effort"]), (model, effort))
                self.assertIn(model, fields["description"].lower())
                self.assertIn(f"| `{stem}` | `{model}` | `{effort}` |", read(SKILLS / "deliver" / "references" / "tiers.md"))

    def test_each_researcher_pins_its_lane_model_and_effort(self):
        docs = agent_docs()
        for stem, (model, effort) in RESEARCHER_MODELS.items():
            with self.subTest(agent=stem):
                fields, _ = docs[stem]
                self.assertEqual((fields["model"], fields["effort"]), (model, effort))
                self.assertIn(model, fields["description"].lower())
                self.assertIn(f"| `{stem}` | `{model}` | `{effort}` |", read(SKILLS / "deliver" / "references" / "tiers.md"))


class RulesTest(unittest.TestCase):
    def test_global_rule_set_is_exactly_brief_git_and_writing(self):
        self.assertEqual({p.name for p in rule_files()}, {"brief.md", "git.md", "writing.md"})

    def test_ruleset_set_is_exactly_typescript_code_style(self):
        self.assertEqual({str(p.relative_to(RULESETS)) for p in ruleset_files()}, {"typescript/code-style.md"})

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

    def test_code_style_names_the_root_heading_that_answers_it(self):
        _, body = parse_frontmatter(read(RULESETS / "typescript" / "code-style.md"))
        self.assertIn("Anchors for code-style.md", section(body, "Anchors a root supplies"))

    def test_every_rule_body_opens_with_a_heading(self):
        for p in [*rule_files(), *ruleset_files()]:
            with self.subTest(rule=p.relative_to(CLAUDE).as_posix()):
                _, body = parse_frontmatter(read(p))
                opening = next((line for line in body.splitlines() if line.strip()), "")
                self.assertTrue(opening.startswith("# "), opening)


class BriefRuleTest(unittest.TestCase):
    def test_each_field_label_appears_exactly_once(self):
        text = read(RULES / "brief.md")
        for label in BRIEF_FIELD_LABELS:
            with self.subTest(label=label):
                self.assertEqual(text.count(label), 1)


class HooksTest(unittest.TestCase):
    def test_manifest_top_level_keys_are_exactly_hooks_and_defaults(self):
        self.assertEqual(set(json.loads(read(MANIFEST))), {"hooks", "defaults"})

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


class ClaudeMdTest(unittest.TestCase):
    def test_at_most_8600_bytes(self):
        self.assertLessEqual((CLAUDE / "CLAUDE.md").stat().st_size, CLAUDE_MD_MAX_BYTES)


class OneHomeTest(unittest.TestCase):
    def test_each_one_home_phrase_lives_only_in_its_home(self):
        for phrase, home in ONE_HOME_PHRASES.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(phrase_homes(phrase), {home})

    def test_each_absent_phrase_occurs_nowhere_in_payload(self):
        for phrase in ABSENT_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertEqual(phrase_homes(phrase), set())


class DescriptionsTest(unittest.TestCase):
    def test_no_description_narrates_with_an_arrow(self):
        for kind, docs in (("skill", skill_docs()), ("agent", agent_docs())):
            for name, (fields, _) in docs.items():
                with self.subTest(kind=kind, name=name):
                    self.assertNotIn("\u2192", fields["description"])


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

    def test_issue_write_gives_each_issue_body_heading_once(self):
        _, body = skill_docs()["issue-write"]
        for heading in ISSUE_BODY_HEADINGS:
            with self.subTest(heading=heading):
                self.assertEqual(body.count(heading), 1)

    def test_issue_write_labels_section_names_every_repository_label_once(self):
        _, body = skill_docs()["issue-write"]
        labels = section(body, "Labels")
        for label in REPOSITORY_LABELS:
            with self.subTest(label=label):
                self.assertEqual(len(re.findall(rf"(?<![\w-]){re.escape(label)}(?![\w-])", labels)), 1)

    def test_issue_write_labels_out_of_queue_line_names_labels_in_order(self):
        _, body = skill_docs()["issue-write"]
        labels = section(body, "Labels")
        line = next(l for l in labels.splitlines() if l.startswith("- Out of the queue"))
        offsets = [line.index(f"`{label}`") for label in OUT_OF_QUEUE_LABELS]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_next_skip_names_out_of_queue_labels_in_order(self):
        _, body = skill_docs()["issue-next"]
        skip = section(body, "Skip")
        offsets = [skip.index(f"`{label}`") for label in OUT_OF_QUEUE_LABELS]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_next_output_names_every_brief_field_it_fills(self):
        _, body = skill_docs()["issue-next"]
        output = section(body, "Output")
        for label in ISSUE_NEXT_BRIEF_FIELDS:
            with self.subTest(label=label):
                self.assertIn(label, output)

    def test_issue_triage_names_each_of_its_eight_sections_once_and_in_order(self):
        _, body = skill_docs()["issue-triage"]
        for heading in ISSUE_TRIAGE_SECTIONS:
            with self.subTest(heading=heading):
                self.assertEqual(body.count(f"\n## {heading}\n"), 1)
        offsets = [body.index(f"\n## {heading}\n") for heading in ISSUE_TRIAGE_SECTIONS]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_triage_body_carries_no_parallel_section_and_no_dispatch_word(self):
        _, body = skill_docs()["issue-triage"]
        self.assertNotIn("\n## Parallel\n", body)
        for word in ISSUE_TRIAGE_DISPATCH_WORDS:
            with self.subTest(word=word):
                self.assertIsNone(re.search(rf"\b{word}\b", body, re.IGNORECASE))

    def test_issue_triage_views_the_named_item_and_lists_the_tracker_only_to_compare(self):
        _, body = skill_docs()["issue-triage"]
        self.assertIn("gh issue view", section(body, "Input"))
        self.assertEqual(body.count("gh issue list"), 1)
        self.assertIn("gh issue list", section(body, "Duplicate"))

    def test_research_complex_points_at_research_and_restates_none_of_its_procedure(self):
        docs = skill_docs()
        _, research = docs["research"]
        _, interpreting = docs["research-complex"]
        self.assertIn("skills/research/SKILL.md", interpreting)
        for heading in RESEARCH_PROCEDURE_HEADINGS:
            with self.subTest(heading=heading):
                self.assertIn(heading, research)
                self.assertNotIn(heading, interpreting)

    def test_every_skill_input_section_references_the_brief_rule(self):
        docs = skill_docs()
        self.assertEqual({name for name, (_, body) in docs.items() if "\n## Input\n" in body}, SKILLS_WITH_INPUT)
        for name in SKILLS_WITH_INPUT:
            with self.subTest(skill=name):
                self.assertIn("rules/brief.md", section(docs[name][1], "Input"))


class DeliverReferencesTest(unittest.TestCase):
    def test_deliver_carries_tiers_and_review_loop(self):
        _, body = skill_docs()["deliver"]
        for name in ("tiers.md", "review-loop.md"):
            with self.subTest(reference=name):
                self.assertTrue((SKILLS / "deliver" / "references" / name).is_file())
                self.assertIn(f"references/{name}", body)


def phrase_homes(phrase):
    return {str(p.relative_to(REPO)) for p in payload_files() if phrase in read(p)}


def assert_description(case, description):
    case.assertTrue(description)
    case.assertLessEqual(len(description), DESCRIPTION_MAX)
    for prefix in ("I ", "You ", "Use this"):
        case.assertFalse(description.startswith(prefix), description)


if __name__ == "__main__":
    unittest.main()
