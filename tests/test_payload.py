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
SCRIPTS = REPO / "scripts"

SPEC = importlib.util.spec_from_file_location("verdict_guard", HOOKS / "verdict-guard.py")
verdict_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verdict_guard)
RENDER_SPEC = importlib.util.spec_from_file_location("render_agents_md", SCRIPTS / "render_agents_md.py")
render_agents_md = importlib.util.module_from_spec(RENDER_SPEC)
RENDER_SPEC.loader.exec_module(render_agents_md)

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
BODY_MAX_LINES = 200
CLAUDE_MD_MAX_BYTES = 8600
MODELS = {"fable", "opus", "sonnet"}
COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}

SKILL_FIELDS_BEYOND_NAME_AND_DESCRIPTION = {
    "research": {"context": "fork", "agent": "researcher-trivial"},
    "research-complex": {"context": "fork", "agent": "researcher-complex"},
    "verify-claim": {"context": "fork", "agent": "verifier"},
    "review-change": {"context": "fork", "agent": "reviewer"},
    "commit-item": {},
    "design-surface": {},
    "plan-phases": {},
    "implement": {},
    "test": {},
    "author-gherkin": {},
    "deliver": {},
    "diagnose-root-cause": {},
    "second-opinion-codex": {},
    "author-skill": {},
    "issue-write": {},
    "issue-next": {},
    "issue-triage": {},
    "issue-question": {},
    "issue-answer": {},
}
SKILLS_WITH_INPUT = {"author-gherkin", "design-surface", "implement", "issue-answer", "issue-next", "issue-question", "issue-triage", "issue-write", "plan-phases", "research", "research-complex", "review-change", "test", "verify-claim"}
AGENT_KEYS = {"name", "description", "color", "model", "effort", "tools"}
DEVELOPER_AGENTS = {"developer-trivial", "developer", "developer-complex"}
RESEARCHER_AGENTS = {"researcher-trivial", "researcher-complex"}
EXPECTED_AGENT_SKILLS = {**{name: ["implement", "test", "diagnose-root-cause", "author-gherkin"] for name in DEVELOPER_AGENTS}, "tester": ["test", "author-gherkin"], "reviewer-complex": ["review-change"]}
EXPECTED_AGENT_MODELS = {
    "developer-trivial": "sonnet",
    "developer": "opus",
    "developer-complex": "fable",
    "recommender": "fable",
    "researcher-trivial": "sonnet",
    "researcher-complex": "fable",
    "reviewer": "opus",
    "reviewer-complex": "fable",
    "tester": "opus",
    "verifier": "opus",
}
EXPECTED_AGENT_COLORS = {
    "developer-trivial": "blue",
    "developer": "blue",
    "developer-complex": "blue",
    "recommender": "purple",
    "researcher-trivial": "red",
    "researcher-complex": "red",
    "reviewer": "yellow",
    "reviewer-complex": "yellow",
    "tester": "cyan",
    "verifier": "green",
}
EXPECTED_AGENTS = {"developer-trivial", "developer", "developer-complex", "recommender", "researcher-trivial", "researcher-complex", "reviewer", "reviewer-complex", "tester", "verifier"}
ROUTED_ONLY_AGENTS = {"recommender", "researcher-trivial", "researcher-complex", "reviewer", "reviewer-complex", "verifier"}
RECOMMENDER_TOOLS = "Read, Grep, Glob, WebFetch, WebSearch"
RESEARCH_PROCEDURE_HEADINGS = ("## Sweep", "## Memo")
CIRCUIT_BREAKER_PASSAGES = (
    "re-tiers",
    "`reviewer-complex`",
    "a defect trip re-tiers the item whose fixes carried the defect",
    "a disagreement trip at any tier, end the run",
)
TIER_ROUTING_ROWS = (
    "| `trivial` | `developer-trivial` | `reviewer` |",
    "| `standard` | `developer` | `reviewer` |",
    "| `complex` | `developer-complex` | `reviewer-complex` |",
)

ONE_HOME_PHRASES = {
    "never pipe through": "claude/CLAUDE.md",
    "three tool calls": "claude/CLAUDE.md",
    "enumerating the population": "claude/CLAUDE.md",
    "structured capability": "claude/CLAUDE.md",
    "re-read the evidence": "claude/CLAUDE.md",
    "a decision not made": "claude/rules/brief.md",
    "Unclear in the brief": "claude/rules/brief.md",
    "copy it aside": "claude/skills/test/SKILL.md",
    "the brief or the specification": "claude/skills/test/SKILL.md",
    "serialisation, formatter or summary can hide the defect under test": "claude/skills/test/SKILL.md",
    "never an action not performed": "claude/rules/brief.md",
    "anything inferred rather than run": "claude/rules/brief.md",
    "every claim about what exists today cites": "claude/skills/design-surface/SKILL.md",
    "root cause": "claude/skills/diagnose-root-cause/SKILL.md",
    "not discriminated from a material alternative": "claude/skills/diagnose-root-cause/SKILL.md",
    "decorrelation": "claude/skills/second-opinion-codex/SKILL.md",
    "One attempt per item": "claude/skills/second-opinion-codex/SKILL.md",
    "the brief is incomplete and the question is above": "claude/skills/review-change/SKILL.md",
    "it is not a round": "claude/skills/deliver/SKILL.md",
    "tier of the code it touches": "claude/skills/deliver/references/tiers.md",
    "unique output": "claude/skills/deliver/references/review-loop.md",
    "reviewed baseline": "claude/skills/deliver/references/review-loop.md",
    "fix delta plus the": "claude/skills/review-change/SKILL.md",
    "wearing a review's clothes": "claude/skills/deliver/references/review-loop.md",
    "needs no ask": "claude/rules/git.md",
    "never a brief line": "claude/rules/git.md",
    "Goal or Acceptance cannot be written": "claude/skills/issue-write/SKILL.md",
    "Depends on #N": "claude/skills/issue-write/SKILL.md",
    "addSubIssue": "claude/skills/issue-write/SKILL.md",
    "addBlockedBy": "claude/skills/issue-write/SKILL.md",
    "have to be weighed for": "claude/skills/deliver/references/tiers.md",
    "bug, feature, enhancement, documentation": "claude/skills/issue-next/SKILL.md",
    "As a <who>, I want <what>, so that <why>": "claude/skills/issue-write/SKILL.md",
    "issue-<slug>.md": "claude/skills/issue-write/SKILL.md",
    "issue-<N>-<purpose>.md": "claude/skills/issue-triage/SKILL.md",
    "edits nothing before the ruling": "claude/skills/issue-triage/SKILL.md",
    "carries no orchestration": "claude/skills/author-skill/SKILL.md",
    "corrected from the evidence": "claude/rules/writing.md",
    "RFC adherence and maximum compatibility": "claude/rules/decisions.md",
    "cannot close is UNVERIFIABLE": "claude/skills/verify-claim/SKILL.md",
    "the reach: which corpus was searched": "claude/skills/research/SKILL.md",
    "at least one scenario, error paths included": "claude/skills/author-gherkin/SKILL.md",
    "returns the question to the recommender once": "claude/skills/issue-question/SKILL.md",
    "One item per message": "claude/skills/issue-answer/SKILL.md",
    "rides on every `gh` call here as two shell words": "claude/skills/issue-question/SKILL.md",
    "A mutation is a valid program or it is nothing": "claude/skills/test/SKILL.md",
    "cp -Rc": "claude/skills/test/references/mutation.md",
    "1.05x on 16 cores": "claude/skills/test/references/mutation.md",
}
ABSENT_PHRASES = {
    "@lindorm": CLAUDE,
    "exhaustive over intent": CLAUDE,
    "The tree is not yours": CLAUDE,
    "returned to the orchestrator verbatim": CLAUDE,
    "Expected values traceable to the brief or spec": SKILLS,
    "this skill writes nothing but": SKILLS,
    "Never describe an action you did not perform": SKILLS,
    "free Codex tier": CLAUDE,
    "`question`": CLAUDE,
}

MEANING_CHANGE_EXAMPLES = "or the meaning of one (what an operator does, which boundary a predicate uses, whether a value counts as absent)"
EXPECTED_VALUES_RATIONALE = "a suite derived from the implementation stays green when the implementation is wrong"
PINNING_TEST_FIRST = "Write the test, run it against the tree with no source file edited yet, and record the failure — test name and the assertion that failed. Only then write the fix and rerun it green."
COPY_ASIDE_ONLY_WHEN_FIX_PRESENT = "only when the fix is already in the tree"
STAGED_FAILURE_WARNING = "A failure staged afterwards by reverting does not count: the helpers and structure the fix introduced stay standing, so what fails is one line's sensitivity, not the defect."
SAMPLED_RUN_LINE_FORM = "A sampled run is one acceptance line of the form `<kind>, <budget> → <result>`"
SAMPLED_RUN_FLAKE_EXAMPLE = '`flake diagnosis, 200 runs of test_render_empty within 10 min → the variable it is sensitive to, or "not reproduced" with the bound`'
SAMPLED_RUN_MISSING_BUDGET = "names a sampled run without its budget returns as a question"
SAMPLED_RUN_DEFAULT = "- **Deterministic unless the brief names a sampled run:**"
SAMPLED_RUN_OUT_OF_THE_GATE = "A sampled run's result lives in its report, never in the gate; a defect it finds enters the suite as a deterministic reproducer, with the seed, input or fault recorded."
SAMPLED_RUN_KINDS = ("Statistical", "Fuzz", "Chaos", "Flake diagnosis")
SAMPLED_RUN_NEIGHBOURS = ("\n## Red-before-green proof\n", "\n## Sampled runs\n", "\n## Verification\n")
SAMPLED_RUN_PERFORMANCE = "Load and soak are performance tests"
SAMPLED_RUN_HARNESS = "A run harness proves it can fail before the budget runs."
SAMPLED_RUN_REPORT = "Every run reports its budget, samples, environment and uncertainty."
SAMPLED_RUN_BOUND = "Zero failures in N bounds the rate; it never shows absence."
SAMPLED_RUN_FIELDS = ("budget", "samples", "environment", "uncertainty")
SAMPLED_RUN_OUTPUT_FIELDS = "per sampled run, its budget, samples, environment and uncertainty"
TESTER_SAMPLED_RUN_KINDS = "a statistical, fuzz, chaos or flake-diagnosis sampled run a brief names with its budget"
DIAGNOSE_ROOT_CAUSE_FLAKE_EXCLUSION = "diagnosing a budgeted flake (test)"
TEST_FEATURE_FILE_EXCLUSION = "a feature file (author-gherkin)"
TEST_DESCRIPTION_MUTATION = "mutating a guard, fallback or branch red to show the tests bite"
MUTATION_DRIVER = "`scripts/mutate.py`"
MUTATION_REFERENCE = "references/mutation.md"
MUTATION_VALID_PROGRAM = "A mutation is a valid program or it is nothing."
MUTATION_REJECTIONS = ("One the compiler refuses", "one that reddens the whole suite", "one that changes what the runner collects")
MUTATION_ROT_IS_LOUD = "An anchor that no longer occurs exactly once is rot, and rot is loud:"
MUTATION_STOP_RULE = "- **Stop rule:**"
MUTATION_DONE = "Done when every mutation holds a verdict other than `ROTTED`"
MUTATION_WORKTREE = "git worktree add --detach <path> <sha>"
MUTATION_SEEDING = "cp -Rc"
MUTATION_CONCURRENCY = "several suites at once measured 1.05x on 16 cores"
MUTATION_INCREMENTAL = "--incremental --tsBuildInfoFile"
AUTHOR_GHERKIN_STEP_WORDS = "no class, method, file or type name in a step"
AUTHOR_GHERKIN_UNDEFINED_STEPS = "Undefined steps are the expected result"
CORRECTNESS_FIRST = "Spend your reasoning on the failure modes the plan flags as tricky — correctness first, speed nowhere."
BOUNDARY_CLASSES = ("Secrets and credentials", "Customer or personal data", "Any path the repository marks confidential")
CHANGE_SET_PER_COMMIT = "One commit per accepted change-set through `/commit-item`; an item may land in several, each reviewed"
CLOSE_AFTER_PUSH = 'the issue closes after that commit is pushed, never before: pushed to the default branch, GitHub closes it; pushed to another branch, `gh issue close N --comment "<hash> <subject>"` runs once the push succeeds.'
COMPLETING_COMMIT_FOOTER = "`Closes #N` only on the commit that completes the item, `Refs #N` on a change-set that leaves it open"
COMPLETES_THE_ITEM_INPUT = "The brief says whether this change-set completes the item; unsaid, the footer is `Refs #N`."
COMMIT_PUSH_CLOSE = "The order is commit, push, close, per `rules/git.md`"
DELIVER_TIERS_EVERY_ITEM = "Tier every item per `references/tiers.md` before it runs"
DELIVER_TRIVIAL_INLINE = "A one-liner tiered `trivial` runs `implement` inline; every other item gets a brief."
DELIVER_TIERING_BYPASS = "runs `implement` directly"
IMPLEMENT_ROW_TIER_GATE = "inline for a one-liner tiered `trivial`, otherwise"
IMPLEMENT_DESCRIPTION_TIER_GATE = "inline for a one-liner tiered trivial, otherwise"
DESIGN_EXIT_RETURNS_THE_DESIGN = "When the surface is locked, return it in the message — internals are Claude's to decide. The chat records it where the project keeps plans and hands it to `deliver`."
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
    "parked",
    "blocked",
    "question: open",
    "question: closed",
    "duplicate",
    "invalid",
    "wontfix",
    "accessibility",
    "good first issue",
    "help wanted",
)
OUT_OF_QUEUE_LABELS = ("parked", "blocked", "question: open", "duplicate", "invalid", "wontfix")
RELATION_MUTATIONS = ("addSubIssue", "addBlockedBy")
ISSUE_NEXT_BRIEF_FIELDS = ("Item:", "Goal:", "Acceptance:", "Decisions made:", "Tier:", "Out of scope:")
ISSUE_NEXT_CLOSED_QUESTION_STAYS = "`question: closed` skips nothing"
GH_REPO_FLAG = "--repo <owner/name>"
GH_CODE_SPAN = re.compile(r"`gh [^`]*`")
QUESTION_COMMENT_HEADING = "## Question"
RULING_COMMENT_HEADING = "## Ruling"
ISSUE_QUESTION_INPUT = "One issue number and the question"
ISSUE_QUESTION_COMMENT = "gh issue comment <N> --body-file <scratchpad file>"
ISSUE_QUESTION_LABEL_EDIT = 'gh issue edit <N> --add-label "question: open" --remove-label "question: closed"'
ISSUE_QUESTION_LABEL_CREATE = "gh label create"
ISSUE_QUESTION_LABEL_RENAME = 'gh label edit question --name "question: open"'
ISSUE_QUESTION_RETRY_ONCE = "returns the question to the recommender once, the verdict attached"
ISSUE_QUESTION_FIX_LIST = "no recommender run"
ISSUE_ANSWER_LABEL_EDIT = 'gh issue edit <N> --remove-label "question: open" --add-label "question: closed"'
ISSUE_ANSWER_ONE_ITEM = "One item per message"
ISSUE_ANSWER_RESTART = "names what restarts"
ISSUE_ANSWER_RESTART_TARGETS = ("`issue-triage`", "`issue-next`")
ISSUE_TRIAGE_THIN_TEXT_REFUSE = "`issue-write` § Refuse"
ISSUE_TRIAGE_THIN_TEXT_FILED = "§ Apply's question row"
DELIVER_DEVIATION_FILED = "when the ruling is the user's, file it through `issue-question` on the item, park the item and continue the loop with the next"
DELIVER_RULING_PREMISE = "a factual premise inside a ruling goes through `/verify-claim` before it enters a brief"
CLAUDE_MD_TRACKER_QUESTION = "A question on a tracker item is filed through `issue-question` and reported in one line; one with no item is asked inline as above."
ISSUE_NEXT_DECISIONS_FROM_RULINGS = "in comment order, or `none`"
ISSUE_TRIAGE_SECTIONS = ("Input", "State", "Draft", "Duplicate", "Critique", "Done", "Apply", "Output")
ISSUE_TRIAGE_DISPATCH_WORDS = (r"lanes?", r"fork(s|ed|ing)?", r"parallel")
DECISION_TIE_BREAKS = ("RFC adherence and maximum compatibility", "readable code", "public interfaces that are easy to use and interpret")


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

    def test_no_skill_takes_a_name_claude_code_reserves(self):
        self.assertEqual({d.name for d in skill_dirs()} & RESERVED_SKILL_NAMES, set())

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

    def test_every_agent_runs_the_model_it_is_pinned_to(self):
        for stem, (fields, _) in agent_docs().items():
            with self.subTest(agent=stem):
                self.assertEqual(fields["model"], EXPECTED_AGENT_MODELS[stem])

    def test_every_sonnet_and_opus_agent_runs_at_xhigh_effort(self):
        for stem, (fields, _) in agent_docs().items():
            if fields["model"] in {"sonnet", "opus"}:
                with self.subTest(agent=stem):
                    self.assertEqual(fields["effort"], "xhigh")

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

    def test_every_agent_carries_the_color_it_is_pinned_to(self):
        for stem, (fields, _) in agent_docs().items():
            with self.subTest(agent=stem):
                self.assertEqual(fields["color"], EXPECTED_AGENT_COLORS[stem])

    def test_agents_sharing_a_family_stem_share_one_color(self):
        families = {}
        for stem, (fields, _) in agent_docs().items():
            families.setdefault(stem.split("-", 1)[0], set()).add(fields["color"])
        for family, colors in families.items():
            with self.subTest(family=family):
                self.assertEqual(len(colors), 1, f"{family} agents do not share one color: {colors}")

    def test_each_routed_only_agent_description_is_one_sentence_under_200_characters(self):
        docs = agent_docs()
        for stem in ROUTED_ONLY_AGENTS:
            with self.subTest(agent=stem):
                description = docs[stem][0]["description"]
                self.assertLess(len(description), 200)
                self.assertEqual(sentence_count(description), 1)

    def test_every_agent_body_is_exactly_two_sentences(self):
        for stem, (_, body) in agent_docs().items():
            with self.subTest(agent=stem):
                self.assertEqual(sentence_count(body), 2)

    def test_tester_names_the_four_sampled_run_kinds_and_returns_their_four_report_fields(self):
        fields, body = agent_docs()["tester"]
        self.assertIn(TESTER_SAMPLED_RUN_KINDS, fields["description"])
        self.assertLess(len(fields["description"]), 200)
        self.assertEqual(sentence_count(fields["description"]), 1)
        for field in SAMPLED_RUN_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, body)

    def test_recommender_is_read_only_at_high_effort_and_dispatched_through_issue_question(self):
        fields, _ = agent_docs()["recommender"]
        self.assertEqual(fields["tools"], RECOMMENDER_TOOLS)
        self.assertEqual(fields["effort"], "high")
        self.assertIn("dispatched through issue-question", fields["description"])

    def test_each_tiered_agent_is_named_once_in_tiers_and_its_description_names_its_frontmatter_model(self):
        docs = agent_docs()
        tiers = read(SKILLS / "deliver" / "references" / "tiers.md")
        for stem in DEVELOPER_AGENTS | RESEARCHER_AGENTS:
            with self.subTest(agent=stem):
                fields, _ = docs[stem]
                self.assertEqual(tiers.count(f"| `{stem}` |"), 1)
                self.assertIn(fields["model"], fields["description"].lower())


class RulesTest(unittest.TestCase):
    def test_global_rule_set_is_exactly_brief_decisions_git_and_writing(self):
        self.assertEqual({p.name for p in rule_files()}, {"brief.md", "decisions.md", "git.md", "writing.md"})

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


class DecisionsRuleTest(unittest.TestCase):
    def test_opens_with_the_decisions_heading_and_orders_the_three_tie_breaks(self):
        text = read(RULES / "decisions.md")
        self.assertTrue(text.startswith("# Decisions\n"))
        offsets = [text.index(tie_break) for tie_break in DECISION_TIE_BREAKS]
        self.assertEqual(offsets, sorted(offsets))

    def test_design_surface_method_points_at_the_tie_breaks_beside_its_one_recommendation_step(self):
        _, body = skill_docs()["design-surface"]
        method = section(body, "Method")
        self.assertIn("rules/decisions.md", method)
        self.assertLess(method.index("one recommendation"), method.index("rules/decisions.md"))


class GitRuleTest(unittest.TestCase):
    def test_an_item_may_land_in_several_reviewed_commits_and_its_issue_closes_after_the_push(self):
        text = re.sub(r"\s+", " ", read(RULES / "git.md"))
        self.assertIn(CHANGE_SET_PER_COMMIT, text)
        self.assertIn(CLOSE_AFTER_PUSH, text)


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

    def test_routing_table_names_every_skill_once(self):
        body = (CLAUDE / "CLAUDE.md").read_text(encoding="utf-8")
        for skill in skill_dirs():
            with self.subTest(skill=skill.name):
                self.assertEqual(body.count(f"| `{skill.name}` |"), 1)

    def test_implement_row_and_description_both_gate_the_inline_path_on_trivial_tier(self):
        body = read(CLAUDE / "CLAUDE.md")
        row = next(line for line in body.splitlines() if line.startswith("| `implement` |"))
        self.assertIn(IMPLEMENT_ROW_TIER_GATE, row)
        fields, _ = skill_docs()["implement"]
        self.assertIn(IMPLEMENT_DESCRIPTION_TIER_GATE, fields["description"])

    def test_a_question_on_a_tracker_item_is_filed_through_issue_question_and_one_without_is_asked_inline(self):
        self.assertIn(CLAUDE_MD_TRACKER_QUESTION, re.sub(r"\s+", " ", read(CLAUDE / "CLAUDE.md")))

    def test_built_in_agent_types_are_dispatched_with_opus(self):
        self.assertIn("a built-in agent type inherits the session's model, so pass `model: opus`", re.sub(r"\s+", " ", read(CLAUDE / "CLAUDE.md")))

    def test_real_tree_render_has_no_line_with_forks_into_or_select_tool_and_keeps_verify_then_claim(self):
        rendered = render_agents_md.render(CLAUDE / "CLAUDE.md", RULES)
        lines = rendered.split("\n")
        self.assertEqual([line for line in lines if "forks into" in line], [])
        self.assertEqual([line for line in lines if "select tool" in line], [])
        self.assertIn("Verify, then claim", rendered)


class OneHomeTest(unittest.TestCase):
    def test_each_one_home_phrase_lives_only_in_its_home(self):
        for phrase, home in ONE_HOME_PHRASES.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(phrase_homes(phrase), {home})

    def test_each_absent_phrase_occurs_nowhere_in_the_tree_that_bars_it(self):
        for phrase, tree in ABSENT_PHRASES.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(phrase_homes(phrase, tree), set())

    def test_phrase_homes_filters_by_the_tree_it_is_given(self):
        phrase = "never an action not performed"
        self.assertEqual(phrase_homes(phrase, SKILLS), set())
        self.assertEqual(phrase_homes(phrase, CLAUDE), {"claude/rules/brief.md"})


class DescriptionsTest(unittest.TestCase):
    def test_no_description_narrates_with_an_arrow(self):
        for kind, docs in (("skill", skill_docs()), ("agent", agent_docs())):
            for name, (fields, _) in docs.items():
                with self.subTest(kind=kind, name=name):
                    self.assertNotIn("\u2192", fields["description"])


class SkillPassagesTest(unittest.TestCase):
    def test_design_description_names_the_meaning_change_examples(self):
        fields, _ = skill_docs()["design-surface"]
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

    def test_test_input_gives_a_sampled_run_its_line_form_and_returns_a_missing_budget_as_a_question(self):
        _, body = skill_docs()["test"]
        acceptance = section(body, "Input")
        for passage in (SAMPLED_RUN_LINE_FORM, SAMPLED_RUN_FLAKE_EXAMPLE, SAMPLED_RUN_MISSING_BUDGET):
            with self.subTest(passage=passage):
                self.assertIn(passage, acceptance)

    def test_test_principles_are_deterministic_unless_the_brief_names_a_sampled_run(self):
        _, body = skill_docs()["test"]
        principles = section(body, "Principles")
        self.assertEqual([line.startswith(SAMPLED_RUN_DEFAULT) for line in principles.splitlines()].count(True), 1)
        self.assertIn(SAMPLED_RUN_OUT_OF_THE_GATE, principles)

    def test_test_sampled_runs_names_each_kind_once_and_leaves_load_and_soak_to_performance_tests(self):
        _, body = skill_docs()["test"]
        for heading in SAMPLED_RUN_NEIGHBOURS:
            self.assertIn(heading, body)
        offsets = [body.index(heading) for heading in SAMPLED_RUN_NEIGHBOURS]
        self.assertEqual(offsets, sorted(offsets))
        runs = section(body, "Sampled runs")
        for kind in SAMPLED_RUN_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(f"- **{kind}:**", runs)
                self.assertEqual(len(re.findall(rf"(?<![\w-]){kind}(?![\w-])", runs, re.IGNORECASE)), 1)
        self.assertIn(SAMPLED_RUN_PERFORMANCE, runs)

    def test_test_reports_each_sampled_run_with_its_budget_samples_environment_and_uncertainty(self):
        _, body = skill_docs()["test"]
        runs = section(body, "Sampled runs")
        output = section(body, "Output")
        for passage in (SAMPLED_RUN_HARNESS, SAMPLED_RUN_REPORT, SAMPLED_RUN_BOUND):
            with self.subTest(passage=passage):
                self.assertIn(passage, runs)
        self.assertIn(SAMPLED_RUN_OUTPUT_FIELDS, output)

    def test_author_gherkin_keeps_implementation_names_out_of_steps_and_quotes_undefined_steps(self):
        _, body = skill_docs()["author-gherkin"]
        self.assertIn(AUTHOR_GHERKIN_STEP_WORDS, section(body, "Scenario shape"))
        self.assertIn(AUTHOR_GHERKIN_UNDEFINED_STEPS, section(body, "Output"))

    def test_diagnose_root_cause_description_excludes_a_budgeted_flake_to_test(self):
        fields, _ = skill_docs()["diagnose-root-cause"]
        self.assertIn(DIAGNOSE_ROOT_CAUSE_FLAKE_EXCLUSION, fields["description"])

    def test_test_description_excludes_a_feature_file_to_author_gherkin(self):
        fields, _ = skill_docs()["test"]
        self.assertIn(TEST_FEATURE_FILE_EXCLUSION, fields["description"])

    def test_test_description_names_mutating_a_guard_red(self):
        fields, _ = skill_docs()["test"]
        self.assertIn(TEST_DESCRIPTION_MUTATION, fields["description"])

    def test_test_mutation_proof_names_the_driver_its_reference_and_the_three_rejections(self):
        _, body = skill_docs()["test"]
        proof = section(body, "Mutation proof")
        for passage in (MUTATION_DRIVER, MUTATION_REFERENCE, MUTATION_VALID_PROGRAM, MUTATION_ROT_IS_LOUD, *MUTATION_REJECTIONS):
            with self.subTest(passage=passage):
                self.assertIn(passage, proof)

    def test_test_mutation_proof_carries_a_stop_rule_and_a_done_condition(self):
        _, body = skill_docs()["test"]
        proof = section(body, "Mutation proof")
        for passage in (MUTATION_STOP_RULE, MUTATION_DONE):
            with self.subTest(passage=passage):
                self.assertIn(passage, proof)

    def test_implement_method_puts_correctness_before_speed(self):
        _, body = skill_docs()["implement"]
        self.assertIn(CORRECTNESS_FIRST, section(body, "Method"))

    def test_second_opinion_codex_boundary_names_the_three_classes_and_the_confidential_file(self):
        _, body = skill_docs()["second-opinion-codex"]
        boundary = section(body, "Boundary")
        for passage in (*BOUNDARY_CLASSES, "`.confidential`"):
            with self.subTest(passage=passage):
                self.assertIn(passage, boundary)

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

    def test_issue_write_create_carries_each_relation_mutation_once(self):
        _, body = skill_docs()["issue-write"]
        create = section(body, "Create")
        for mutation in RELATION_MUTATIONS:
            with self.subTest(mutation=mutation):
                self.assertEqual(body.count(mutation), 1)
                self.assertIn(mutation, create)

    def test_issue_next_skip_names_out_of_queue_labels_in_order(self):
        _, body = skill_docs()["issue-next"]
        skip = section(body, "Skip")
        offsets = [skip.index(f"`{label}`") for label in OUT_OF_QUEUE_LABELS]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_next_skip_reads_blockers_and_pieces_from_the_relations(self):
        _, body = skill_docs()["issue-next"]
        skip = section(body, "Skip")
        for field in ("blockedBy", "subIssues"):
            with self.subTest(field=field):
                self.assertIn(field, skip)
        self.assertNotIn("--json state", body)

    def test_issue_next_output_names_every_brief_field_it_fills(self):
        _, body = skill_docs()["issue-next"]
        output = section(body, "Output")
        for label in ISSUE_NEXT_BRIEF_FIELDS:
            with self.subTest(label=label):
                self.assertIn(label, output)

    def test_issue_next_lets_a_closed_question_through_and_fills_decisions_made_from_its_ruling_comments(self):
        _, body = skill_docs()["issue-next"]
        self.assertIn(ISSUE_NEXT_CLOSED_QUESTION_STAYS, section(body, "Skip"))
        output = section(body, "Output")
        self.assertIn(ISSUE_NEXT_DECISIONS_FROM_RULINGS, output)
        self.assertLess(output.index("Decisions made:"), output.index(ISSUE_NEXT_DECISIONS_FROM_RULINGS))

    def test_issue_question_takes_one_item_and_every_gh_call_in_the_question_skills_carries_the_repo_as_two_words(self):
        docs = skill_docs()
        self.assertIn(ISSUE_QUESTION_INPUT, section(docs["issue-question"][1], "Input"))
        for name in ("issue-question", "issue-answer"):
            spans = GH_CODE_SPAN.findall(docs[name][1])
            self.assertTrue(spans, name)
            for span in spans:
                with self.subTest(skill=name, call=span):
                    self.assertIn(GH_REPO_FLAG, span)

    def test_issue_question_files_one_comment_then_swaps_the_labels_and_repairs_the_label_set(self):
        _, body = skill_docs()["issue-question"]
        method = section(body, "Method")
        for passage in (QUESTION_COMMENT_HEADING, ISSUE_QUESTION_COMMENT, ISSUE_QUESTION_LABEL_EDIT, ISSUE_QUESTION_LABEL_CREATE, ISSUE_QUESTION_LABEL_RENAME):
            with self.subTest(passage=passage):
                self.assertIn(passage, method)
        self.assertLess(method.index(ISSUE_QUESTION_COMMENT), method.index(ISSUE_QUESTION_LABEL_EDIT))

    def test_issue_question_retries_the_recommender_once_on_a_disproven_claim_and_never_for_a_fix_list(self):
        _, body = skill_docs()["issue-question"]
        method = section(body, "Method")
        self.assertIn("/verify-claim", method)
        self.assertIn("DISPROVEN", method)
        self.assertEqual(method.count(ISSUE_QUESTION_RETRY_ONCE), 1)
        self.assertIn(ISSUE_QUESTION_FIX_LIST, method)

    def test_issue_answer_presents_one_item_under_questions_then_posts_the_ruling_and_closes_the_question(self):
        _, body = skill_docs()["issue-answer"]
        self.assertIn("`issue-next` § Order", section(body, "Input"))
        self.assertIn("`## Questions`", body)
        self.assertIn(RULING_COMMENT_HEADING, body)
        self.assertIn(ISSUE_ANSWER_LABEL_EDIT, body)
        self.assertLess(body.index("gh issue comment"), body.index(ISSUE_ANSWER_LABEL_EDIT))
        self.assertEqual(body.count(ISSUE_ANSWER_ONE_ITEM), 1)

    def test_issue_answer_rule_names_what_restarts_after_the_label_edit_the_triage_or_the_queue(self):
        _, body = skill_docs()["issue-answer"]
        rule = section(body, "Rule")
        self.assertIn(ISSUE_ANSWER_RESTART, rule)
        self.assertLess(rule.index(ISSUE_ANSWER_LABEL_EDIT), rule.index(ISSUE_ANSWER_RESTART))
        restart = next(line for line in rule.splitlines() if ISSUE_ANSWER_RESTART in line)
        for target in ISSUE_ANSWER_RESTART_TARGETS:
            with self.subTest(target=target):
                self.assertIn(target, restart)

    def test_the_ruling_comment_shape_is_fixed_in_issue_answer_and_cited_by_issue_next(self):
        docs = skill_docs()
        output = section(docs["issue-next"][1], "Output")
        self.assertIn(RULING_COMMENT_HEADING, output)
        self.assertIn("`issue-answer`", output)
        self.assertIn(RULING_COMMENT_HEADING, docs["issue-answer"][1])
        self.assertIn(QUESTION_COMMENT_HEADING, docs["issue-answer"][1])

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

    def test_issue_triage_split_files_pieces_as_sub_issues_and_leaves_the_calls_to_issue_write(self):
        _, body = skill_docs()["issue-triage"]
        rulings = section(body, "Apply")
        split = next(l for l in rulings.splitlines() if l.startswith("- split —"))
        self.assertIn("sub-issue of the original", split)
        self.assertIn("blocked-by relation", split)
        self.assertIn("the two calls in `issue-write` § Create", rulings)
        for mutation in RELATION_MUTATIONS:
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, body)

    def test_issue_triage_revise_and_question_rows_file_through_issue_question_and_add_no_label_themselves(self):
        _, body = skill_docs()["issue-triage"]
        rulings = section(body, "Apply")
        for prefix in ("- revise —", "- question —"):
            with self.subTest(row=prefix):
                line = next(l for l in rulings.splitlines() if l.startswith(prefix))
                self.assertIn("`issue-question`", line)
        self.assertNotIn("-label question", body)
        self.assertIn("`question: closed`", rulings)

    def test_issue_triage_draft_borrows_refuse_only_to_name_the_missing_sentence_and_files_it_as_the_question_row_says(self):
        _, body = skill_docs()["issue-triage"]
        draft = section(body, "Draft")
        bullet = next(line for line in draft.splitlines() if ISSUE_TRIAGE_THIN_TEXT_REFUSE in line)
        self.assertIn("missing sentence", bullet)
        self.assertIn(ISSUE_TRIAGE_THIN_TEXT_FILED, bullet)
        self.assertNotIn("to the user", bullet)

    def test_issue_skills_enumerate_the_full_queue_labels_and_duplicate_set(self):
        for skill, heading, call in (
            ("issue-next", "Order", "gh issue list --state open --limit 1000 --json number,title,labels,body"),
            ("issue-triage", "Duplicate", "gh issue list --state open --limit 1000 --json number,title,body"),
            ("issue-write", "Labels", "gh label list --limit 1000"),
        ):
            with self.subTest(skill=skill):
                _, body = skill_docs()[skill]
                self.assertIn(call, section(body, heading))

    def test_deliver_rounds_name_both_review_routes_and_point_at_tiers(self):
        _, body = skill_docs()["deliver"]
        rounds = section(body, "Rounds")
        for passage in ("`reviewer` through `/review-change`", "`reviewer-complex` dispatched by the chat", "`references/tiers.md`"):
            with self.subTest(passage=passage):
                self.assertIn(passage, rounds)

    def test_deliver_rounds_file_a_deviation_needing_the_user_through_issue_question_and_verify_a_ruling_premise(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Rounds").splitlines() if "is a deviation:" in line)
        self.assertIn(DELIVER_DEVIATION_FILED, bullet)
        self.assertIn(DELIVER_RULING_PREMISE, bullet)

    def test_commit_item_footers_the_completing_commit_and_closes_no_issue_itself(self):
        fields, body = skill_docs()["commit-item"]
        self.assertNotIn("close", fields["description"].lower())
        self.assertNotIn("gh issue close", body)
        self.assertIn(COMPLETING_COMMIT_FOOTER, section(body, "Steps"))
        self.assertIn(COMPLETES_THE_ITEM_INPUT, section(body, "Preconditions"))

    def test_deliver_before_commit_orders_commit_push_close_by_the_git_rule(self):
        _, body = skill_docs()["deliver"]
        self.assertIn(COMMIT_PUSH_CLOSE, section(body, "Before commit"))

    def test_deliver_intake_tiers_every_item_and_runs_only_a_trivial_one_liner_inline(self):
        _, body = skill_docs()["deliver"]
        intake = section(body, "Intake and tiering")
        self.assertIn(DELIVER_TIERS_EVERY_ITEM, intake)
        self.assertIn(DELIVER_TRIVIAL_INLINE, intake)
        self.assertNotIn(DELIVER_TIERING_BYPASS, body)

    def test_design_surface_exit_returns_the_locked_design_and_instructs_no_write(self):
        _, body = skill_docs()["design-surface"]
        self.assertIn(DESIGN_EXIT_RETURNS_THE_DESIGN, section(body, "Exit"))
        self.assertNotIn("writ", body.lower())

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

    def test_tier_routing_pairs_each_developer_with_the_reviewer_that_reviews_its_items(self):
        tiers = read(SKILLS / "deliver" / "references" / "tiers.md")
        for row in TIER_ROUTING_ROWS:
            with self.subTest(row=row):
                self.assertEqual(tiers.count(row), 1)

    def test_circuit_breaker_re_tiers_a_defect_trip_and_ends_the_run_on_a_disagreement(self):
        bullet = next(line for line in read(SKILLS / "deliver" / "references" / "review-loop.md").splitlines() if line.startswith("- **Circuit breaker.**"))
        for passage in CIRCUIT_BREAKER_PASSAGES:
            with self.subTest(passage=passage):
                self.assertIn(passage, bullet)


class TestReferencesTest(unittest.TestCase):
    def test_test_carries_the_mutation_reference_and_names_it(self):
        _, body = skill_docs()["test"]
        self.assertTrue((SKILLS / "test" / "references" / "mutation.md").is_file())
        self.assertIn(MUTATION_REFERENCE, body)

    def test_the_mutation_reference_seeds_a_worktree_and_warns_that_concurrency_buys_nothing(self):
        reference = read(SKILLS / "test" / "references" / "mutation.md")
        for passage in (MUTATION_WORKTREE, MUTATION_SEEDING, MUTATION_CONCURRENCY, MUTATION_INCREMENTAL):
            with self.subTest(passage=passage):
                self.assertIn(passage, reference)


def phrase_homes(phrase, tree=CLAUDE):
    return {str(p.relative_to(REPO)) for p in payload_files() if p.is_relative_to(tree) and phrase in read(p)}


def assert_description(case, description):
    case.assertTrue(description)
    case.assertLessEqual(len(description), DESCRIPTION_MAX)
    for prefix in ("I ", "You ", "Use this"):
        case.assertFalse(description.startswith(prefix), description)


if __name__ == "__main__":
    unittest.main()
