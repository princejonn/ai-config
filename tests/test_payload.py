import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
GUARD_SPEC = importlib.util.spec_from_file_location("git_guard", HOOKS / "git-guard.py")
git_guard = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(git_guard)
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
    "research": {},
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
SKILLS_WITH_INPUT = {"author-gherkin", "design-surface", "implement", "issue-answer", "issue-next", "issue-question", "issue-triage", "issue-write", "plan-phases", "research", "review-change", "test", "verify-claim"}
AGENT_KEYS = {"name", "description", "color", "model", "effort", "tools"}
DEVELOPER_AGENTS = {"developer-trivial", "developer", "developer-complex"}
RESEARCHER_AGENTS = {"researcher-trivial", "researcher", "researcher-complex"}
EXPECTED_AGENT_SKILLS = {
    **{name: ["implement", "test", "diagnose-root-cause", "author-gherkin"] for name in DEVELOPER_AGENTS},
    **{name: ["research"] for name in RESEARCHER_AGENTS},
    "tester": ["test", "author-gherkin"],
    "reviewer-complex": ["review-change"],
    "issue-writer": ["issue-write"],
}
EXPECTED_AGENT_MODELS = {
    "developer-trivial": "sonnet",
    "developer": "opus",
    "developer-complex": "fable",
    "issue-writer": "opus",
    "recommender": "fable",
    "researcher-trivial": "sonnet",
    "researcher": "opus",
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
    "issue-writer": "orange",
    "recommender": "purple",
    "researcher-trivial": "red",
    "researcher": "red",
    "researcher-complex": "red",
    "reviewer": "yellow",
    "reviewer-complex": "yellow",
    "tester": "cyan",
    "verifier": "green",
}
EXPECTED_AGENTS = {"developer-trivial", "developer", "developer-complex", "issue-writer", "recommender", "researcher-trivial", "researcher", "researcher-complex", "reviewer", "reviewer-complex", "tester", "verifier"}
ROUTED_ONLY_AGENTS = {"issue-writer", "recommender", "researcher-trivial", "researcher", "researcher-complex", "reviewer", "reviewer-complex", "verifier"}
RECOMMENDER_TOOLS = "Read, Grep, Glob, WebFetch, WebSearch"
ISSUE_WRITER_TOOLS = "Agent, Skill, Bash, Read, Write, Grep, Glob"
ISSUE_WRITER_DISPATCH = "dispatched by the chat in the background, one per discussion"
ISSUE_WRITER_BODY = (
    "You run issue-write on each item one discussion with the user yields",
    "from the user's words the brief quotes under `Decisions made:`",
    "creating the items in dependency order so every dependency line names a number already created",
    "file each open question on a created item through issue-question, `Filed from: issue-write`",
    "What you dispatch reports back only after a turn boundary, so you end your turn and resume on each result",
    "create an item only once its issue-write § Check verdicts are in",
    "hand back only once every verdict and every filed question is in",
    'one line per item, its number, its URL and each question filed or "no open questions"',
    "or what issue-write § Refuse or § Check returned in its place",
)
RESEARCHER_DISPATCH = "dispatched by the chat per the research routing in tiers.md"
RESEARCH_LANE_KINDS = ("enumerates", "interprets")
NOT_INVOKED_DIRECTLY = "not invoked directly"
DISPATCHED_THROUGH_A_SKILL = re.compile(r"dispatched through /?([a-z0-9-]+)")
BROAD_GATHERING_TO_RESEARCH = "broad source gathering (research)"
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
RESEARCH_ROUTING_ROWS = (
    "| `trivial` | enumerates | `researcher-trivial` |",
    "| `standard` | interprets | `researcher` |",
    "| `complex` | interprets for a complex-tier item | `researcher-complex` |",
)

ONE_HOME_PHRASES = {
    "never pipe through": "claude/CLAUDE.md",
    "three tool calls": "claude/CLAUDE.md",
    "enumerating the population": "claude/CLAUDE.md",
    "structured capability": "claude/CLAUDE.md",
    "re-read the evidence": "claude/CLAUDE.md",
    "as the user prefers": "claude/CLAUDE.md",
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
    "chore(paused)": "claude/skills/deliver/SKILL.md",
    "tier of the code it touches": "claude/skills/deliver/references/tiers.md",
    "unique output": "claude/skills/deliver/references/review-loop.md",
    "reviewed baseline": "claude/skills/deliver/references/review-loop.md",
    "fix delta plus the": "claude/skills/review-change/SKILL.md",
    "wearing a review's clothes": "claude/skills/deliver/references/review-loop.md",
    "needs no ask": "claude/rules/git.md",
    "never a brief line": "claude/rules/git.md",
    "the commits that land its change-sets": "claude/rules/git.md",
    "a push to `main` asks": "claude/rules/git.md",
    "Goal or Acceptance cannot be written": "claude/skills/issue-write/SKILL.md",
    "A finding made during work is raised with the user, not filed": "claude/skills/issue-write/SKILL.md",
    "Depends on #N": "claude/skills/issue-write/SKILL.md",
    "addSubIssue": "claude/skills/issue-write/SKILL.md",
    "addBlockedBy": "claude/skills/issue-write/SKILL.md",
    "have to be weighed for": "claude/skills/deliver/references/tiers.md",
    "how hard an item is to get right": "claude/skills/deliver/references/tiers.md",
    "Tie-break to standard": "claude/skills/deliver/references/tiers.md",
    "counts as interpreting": "claude/skills/deliver/references/tiers.md",
    "An interpreting lane with no item is standard": "claude/skills/deliver/references/tiers.md",
    "re-runs at complex": "claude/skills/deliver/references/tiers.md",
    "splits into one issue per feature": "claude/skills/issue-write/SKILL.md",
    "bug, feature, enhancement, documentation": "claude/skills/issue-next/SKILL.md",
    "overriding what it names": "claude/skills/issue-next/SKILL.md",
    "As a <who>, I want <what>, so that <why>": "claude/skills/issue-write/SKILL.md",
    "issue-<slug>.md": "claude/skills/issue-write/SKILL.md",
    "issue-<N>-<purpose>.md": "claude/skills/issue-triage/SKILL.md",
    "Is #N ready to deliver as briefed?": "claude/skills/issue-triage/SKILL.md",
    "git branch -r --contains": "claude/skills/issue-triage/SKILL.md",
    "carries no orchestration": "claude/skills/author-skill/SKILL.md",
    "corrected from the evidence": "claude/rules/writing.md",
    "with the answer": "claude/rules/writing.md",
    "RFC adherence and maximum compatibility": "claude/rules/decisions.md",
    "the specification's reading wins": "claude/rules/decisions.md",
    "a cited specification section settles": "claude/CLAUDE.md",
    "cannot close is UNVERIFIABLE": "claude/skills/verify-claim/SKILL.md",
    "the reach: which corpus was searched": "claude/skills/research/SKILL.md",
    "at least one scenario, error paths included": "claude/skills/author-gherkin/SKILL.md",
    "returns the question to the recommender once": "claude/skills/issue-question/SKILL.md",
    "no recommender run": "claude/skills/issue-question/SKILL.md",
    "One item per message": "claude/skills/issue-answer/SKILL.md",
    "answers the earliest unanswered `## Question` before it": "claude/skills/issue-answer/SKILL.md",
    "until its ## Ruling is posted": "claude/skills/issue-question/SKILL.md",
    "rides on every `gh` call here as two shell words": "claude/skills/issue-question/SKILL.md",
    "A mutation is a valid program or it is nothing": "claude/skills/test/SKILL.md",
    "cp -Rc": "claude/skills/test/references/mutation.md",
    "1.05x on 16 cores": "claude/skills/test/references/mutation.md",
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
GIT_PUSH_AFTER_COMMIT = "Each commit is followed by a push of its branch, `git push origin <branch>`."
GIT_DONE_ON_A_REMOTE_BRANCH = "An item is done when a remote branch carries the commits that land its change-sets, merged to the default branch or not."
CLOSE_AFTER_PUSH = f'{GIT_PUSH_AFTER_COMMIT} {GIT_DONE_ON_A_REMOTE_BRANCH} The `Closes #N` footer goes on the commit that completes the item, and the issue closes after that commit is pushed, never before: pushed to the default branch, GitHub closes it; pushed to another branch, `gh issue close N --comment "<hash> <subject>"` runs once the push succeeds.'
GIT_PUSH_ASKS_ONLY_ON_MAIN = "a push is not an external call — a push to `main` asks through the permission prompt, a push to any other branch needs no ask;"
GIT_ITEM_FROM_A_DISCUSSION = "closing the item's tracker reference belongs to the item and needs no ask, and an item that comes out of a discussion with the user is created on that discussion; no item is created automatically."
GIT_PAUSED_WORK_EXCEPTION = "paused work is committed and pushed to its `paused/<N>-<k>` branch, never to the default branch, per `deliver`; it reaches the working branch only uncommitted, inside the reviewed change-set"
COMPLETING_COMMIT_FOOTER = "`Closes #N` only on the commit that completes the item, `Refs #N` on a change-set that leaves it open"
COMPLETES_THE_ITEM_INPUT = "The brief says whether this change-set completes the item; unsaid, the footer is `Refs #N`."
COMMIT_PUSH_CLOSE = "The order is commit, push, close, per `rules/git.md`"
COMMIT_ITEM_CONFIRMS_THE_COMMIT = "`git show --name-only`"
COMMIT_ITEM_PUSH = "`git push origin <branch>`, `<branch>` the name `git branch --show-current` prints, written literally and unquoted"
COMMIT_ITEM_REPORT = "Report the hash, the paths, the pushed branch or that the push was declined or failed"
COMMIT_ITEM_CLOSES_AFTER_THE_PUSH = "the issue closes after the push, per `rules/git.md`"
COMMIT_ITEM_DESCRIPTION_PUSH = "and pushes its branch"
DELIVER_TIERS_EVERY_ITEM = "Tier every item per `references/tiers.md` before it runs"
DELIVER_TRIVIAL_INLINE = "A one-liner tiered `trivial` runs `implement` inline; every other item gets a brief."
DELIVER_INTAKE_BRIEF_FROM_ISSUE_NEXT = "A tracker item's brief is the `## Brief` comment `issue-next` hands out, later rulings under `Decisions made:` included."
DELIVER_INTAKE_PATHS_RESOLVE_AT_THE_ROOT = "Its paths are repo-relative; the brief written for the agent resolves each against the repository root."
DELIVER_INTAKE_PLAN_COMMENT = "For `tier: complex`, the item's latest `## Plan` comment is what `plan-phases` details into the plan the brief carries."
DELIVER_INTAKE_CHECKS_THE_BRIEF = "Before the item runs, inline or dispatched, the brief is checked against the tree."
DELIVER_INTAKE_CONTRADICTION = (
    "A file it names that is gone, or a premise `/verify-claim` returns `DISPROVEN` for, contradicts the brief",
    "filed as a question through `issue-question` on the item, `Filed from: deliver § Intake`",
    "the filing takes `ready` off",
    "nothing runs",
)
DELIVER_INTAKE_FILED_FROM = "deliver § Intake"
IMPLEMENT_ROW_TIER_GATE = "inline for a one-liner tiered `trivial`, otherwise"
IMPLEMENT_DESCRIPTION_TIER_GATE = "inline for a one-liner tiered trivial, otherwise"
RESEARCH_ROW_AGENT = "in the tier's researcher agent"
RESEARCH_DESCRIPTION_AGENT = "in a researcher agent"
DELIVER_RESEARCH_READS = "Bulk and interpreting reads go to the tier's researcher per `references/tiers.md`"
DELIVER_MEMO_ENTERS_THE_BRIEF = "the memo, not the material, enters the brief"
DESIGN_EXIT_RETURNS_THE_DESIGN = "When the surface is locked, return it in the message — internals are Claude's to decide. The chat posts it on the tracker item as a comment opening `## Design` (`gh issue comment <N> --body-file <scratchpad file>`) — with no item, records it where the project keeps plans — and hands it to `deliver`, or back to `issue-triage` when triage ran it."
DESIGN_DESCRIPTION_MODES = "inline with the user or inside issue-triage on an item with nothing asked of them"
DESIGN_ROW_MODES = "with the user before code, or inside `issue-triage` without them"
DESIGN_CLAIMS_VERIFIED_BEFORE_THE_USER_OR_TRIAGE = "Load-bearing claims go to `verify-claim` before a proposal reaches the user, or returns to `issue-triage` when triage ran it."
DESIGN_USER_DECISION_PUT_OR_RETURNED = "what needs a user decision: put to the user, or returned as a finding for `issue-triage` to hold when triage ran it, nothing asked of the user, and the surface not locked until the ruling restarts triage"
BRIEF_FIELD_LABELS = ("Goal:", "Item:", "Acceptance:", "Files in scope:", "Decisions made:", "Verification:", "Invariant:", "Instructions:", "Tier:", "Out of scope:")
ISSUE_BODY_HEADINGS = ("## Goal", "## Why", "## Proposal", "## Acceptance", "## Related")
REPOSITORY_LABELS = (
    "bug",
    "feature",
    "enhancement",
    "documentation",
    "story",
    "priority: blocker",
    "priority: high",
    "priority: medium",
    "priority: low",
    "tier: trivial",
    "tier: standard",
    "tier: complex",
    "ready",
    "paused",
    "question",
    "parked",
    "blocked",
    "invalid",
    "wontfix",
    "accessibility",
    "good first issue",
    "help wanted",
)
STATUS_LABELS = ("ready", "paused")
HOLD_LABELS = ("question", "parked", "blocked", "invalid", "wontfix")
GH_LABEL_NAME = r'(?:"([^"]+)"|([^\s`<"]+))'
GH_LABEL_ARGUMENT = re.compile(rf'(?:--(?:add-|remove-)?label[ =]|gh label (?:create|delete) |gh label edit (?:(?=[^`\n]*? (?:--name[ =]|-n ){GH_LABEL_NAME}))?){GH_LABEL_NAME}')
GH_LABEL_SHORTHAND_CALL = re.compile(r'gh (?:issue (?:list|ls|create|new)|pr (?:list|ls|create|new)|discussion (?:list|ls|create)) [^`\n]*')
GH_LABEL_SHORTHAND_ARGUMENT = re.compile(rf'(?<=\s)-l {GH_LABEL_NAME}')
ISSUE_WRITE_PRIORITY_BULLET = "- Priority: `priority: blocker`, `priority: high`, `priority: medium` or `priority: low` — the tracker's own label descriptions decide which (`gh label list --limit 1000`)."
ISSUE_WRITE_STATUS_BULLET = "- Status, never written here: `ready`, taken by `deliver` as it stands; `paused`, started and stopped, handed out after blocker-priority items and before the rest. An open item carries at most one of the two and is in the backlog with neither; a label on a closed item is inert."
ISSUE_WRITE_STATUS_LINE = "- Status, never written here:"
ISSUE_WRITE_STATUS_AT_MOST_ONE = "An open item carries at most one of the two and is in the backlog with neither"
ISSUE_WRITE_HOLDS_LINE = "- Holds, out of the queue whatever the status, never written here:"
RELATION_MUTATIONS = ("addSubIssue", "addBlockedBy")
ISSUE_WRITE_DESCRIPTION_TRIGGER = "Use when a discussion with the user yields a finding, a request, an idea or a user story to add as an issue"
ISSUE_WRITE_ROW_TRIGGER = "a discussion with the user yields items to add"
ISSUE_WRITE_ROW_INTAKE = (
    "one `issue-writer` per discussion, in the background",
    "the user's words verbatim under the brief's `Decisions made:`",
    "the chat carries on in the same turn",
    "when it returns, relays its one line per item",
    "starts `issue-triage` on each new item unasked",
)
ISSUE_WRITE_INPUT_FROM_A_DISCUSSION = "A title and a description, however rough, from a discussion with the user."
ISSUE_WRITE_FINDING_RAISED_NOT_FILED = "A finding made during work is raised with the user, not filed."
ISSUE_WRITE_INPUT_THE_SET = "The other items the same discussion yields, the rest of the set, come with it for § Check."
ISSUE_WRITE_SECTIONS = ("Input", "Shape", "Labels", "Refuse", "Check", "Create", "Output")
ISSUE_WRITE_CHECK_GATE = "Every item § Refuse lets through is checked before § Create; one a check stops gets nothing created and returns what stopped it."
ISSUE_WRITE_CHECK_BULLETS = {
    "- Duplicate:": (
        "`issue-triage` § Duplicate's comparison set and sameness test, applied to the tracker and to the rest of the set",
        "An open item with the same Goal stops it, returned by number",
        "and so does an item earlier in the set, returned by title",
        "a closed one stops nothing here",
    ),
    "- Evidence:": (
        "each load-bearing § Why claim goes through `/verify-claim`",
        "A `DISPROVEN` claim is corrected from the verdict's evidence or struck",
        "a Goal that rests on a struck claim stops the item, returned with the verdict",
        "an `UNVERIFIABLE` claim stops nothing here, and `issue-triage` § Critique judges it",
    ),
    "- Done:": (
        "the Goal read against the tree",
        "A file:line that already satisfies it stops the item, returned with it",
    ),
}
ISSUE_WRITE_CHECK_DEPENDENTS = "A dependent follows its blocker in the set: a blocker stopped as a duplicate is replaced in the dependent's dependency line by the open item it matched, and a blocker refused or stopped otherwise leaves the dependent uncreated too, returned with the blocker's reason."
ISSUE_WRITE_CHECK_LEAVES_TRIAGE = "The critique and a verdict per acceptance line stay `issue-triage`'s, its § Critique and § Done on the created item."
ISSUE_TRIAGE_CRITIQUE_WHY_LINE = "each § Why claim verifies at the file:line or probe it cites"
ISSUE_WRITE_FILED_FROM = "issue-write"
ISSUE_TRIAGE_SAMENESS_TEST = "never by scoring their similarity, never by a shared subject alone"
ISSUE_WRITE_OUTPUT_STOPPED = "Or, with nothing created, the question § Refuse returns or what stopped the item in § Check."
ISSUE_WRITE_CREATE_STEP_1 = "1. An item is created only out of a discussion with the user, which is the word for every item it yields; nothing creates one automatically (`rules/git.md`)."
ISSUE_WRITE_CREATE_STEPS = (
    "1. An item is created only out of a discussion with the user",
    "2. Write the body to the session scratchpad",
    "3. `gh issue create",
    "4. The relations the item stands in",
    "5. For `tier: complex`, when the discussion settled the plan",
)
ISSUE_WRITE_PLAN_STEP = (
    "`tier: complex`",
    "when the discussion settled the plan",
    "a `## Plan` comment in the shape `issue-triage` § Ready gives",
    "named as `issue-triage` § Ready names one",
    "`gh issue comment <N> --body-file <scratchpad file>`",
)
ISSUE_NEXT_BRIEF_FIELDS = ("Item:", "Goal:", "Acceptance:", "Decisions made:", "Tier:", "Out of scope:")
ISSUE_NEXT_HOLD_LABELS = "The holds are the labels"
ISSUE_NEXT_HELD_WHATEVER_STATUS = "a held item is out of the queue whatever its status"
ISSUE_NEXT_HOLD_REPORTED = "reported with the label that skipped it"
ISSUE_NEXT_SKIPPED_REPORTED = "Then the items skipped above it, each with the open number or the label that skipped it"
ISSUE_NEXT_DESCRIPTION_ORDER = "Returns the next open item from the tracker as the fields a brief needs, ordered `priority: blocker` first, then by status, then urgency, and blocked by nothing open."
ISSUE_NEXT_PRIORITY_ORDER = "1. Priority label: blocker, then high, then medium, then low, then unlabelled."
ISSUE_NEXT_LAST_SORT_KEY = "3. Within that: the lowest number."
ISSUE_NEXT_GROUPS = "The sorted list then splits into four groups, each keeping its order: the items carrying `priority: blocker`, whatever their status, then of the rest the items carrying `paused`, then those carrying `ready`, then the backlog, which carries neither."
ISSUE_NEXT_WALK_THE_GROUPS = "Walk the groups in turn and stop at the first item § Skip lets through."
ISSUE_NEXT_EVERY_ITEM_HELD = "When every item is held, report the list and stop."
ISSUE_NEXT_BACKLOG_TO_TRIAGE = "A backlog winner leaves flagged as one to triage, not to deliver."
ISSUE_NEXT_READY_LEAVES_AS_ITS_BRIEF = "A `ready` or `paused` winner leaves as its latest `## Brief` comment, in the shape `issue-triage` § Ready posts it, with each `## Ruling` posted after that comment added under `Decisions made:`."
ISSUE_NEXT_NO_BRIEF_LEAVES_AS_BACKLOG = "One with no `## Brief` leaves as a backlog winner does."
ISSUE_NEXT_BACKLOG_DERIVED = "A backlog winner leaves as these fields, derived from the state:"
GH_REPO_FLAG = "--repo <owner/name>"
GH_CODE_SPAN = re.compile(r"`gh [^`]*`")
QUESTION_COMMENT_HEADING = "## Question"
RULING_COMMENT_HEADING = "## Ruling"
QUESTION_LABEL_DESCRIPTION = '"An unanswered ## Question comment: out of the queue until its ## Ruling is posted"'
ISSUE_QUESTION_INPUT = "One issue number and the question"
ISSUE_QUESTION_COMMENT = "gh issue comment <N> --body-file <scratchpad file>"
ISSUE_QUESTION_LABEL_EDIT = "`gh issue edit <N> --add-label question --repo <owner/name>`"
ISSUE_QUESTION_LABEL_EDIT_READY = "`gh issue edit <N> --add-label question --remove-label ready --repo <owner/name>` when the list holds `ready`"
ISSUE_QUESTION_LABEL_ADOPT = '`gh label edit question --description "<description>" --repo <owner/name>`'
ISSUE_QUESTION_LABEL_CREATE = '`gh label create question --description "<description>" --repo <owner/name>`'
ISSUE_QUESTION_RETRY_ONCE = "returns the question to the recommender once, the verdict attached"
ISSUE_QUESTION_READY_QUESTION_NO_RECOMMENDER = "The ready question `issue-triage` § Ready files is filed as its own recommendation, with no recommender run."
ISSUE_QUESTION_FILERS = ("`issue-write` for an open question on an item it created", "`issue-triage` for a held finding or the ready question", "`deliver` for a deviation", "`deliver § Intake` for a `## Brief` the tree contradicts")
ISSUE_QUESTION_FILED_FROM = "Filed from: <issue-write | issue-triage | deliver | deliver § Intake>"
ISSUE_QUESTION_VIEW = "`gh issue view <N> --json body,comments --repo <owner/name>`"
ISSUE_QUESTION_STATE_CITES_ISSUE_NEXT = "its state is its body and every comment, read as `issue-next` § Output reads them"
ISSUE_QUESTION_RECOMMENDER_STATE = "the item's state, the question and the files it turns on"
ISSUE_ANSWER_LIST = "`gh issue list --state open --limit 1000 --label question --json number,title,labels,comments --repo <owner/name>`"
ISSUE_ANSWER_PICK_UNANSWERED = "lists with a `## Question` still unanswered"
ISSUE_ANSWER_PASSED_OVER = "The items the pick passes over are named in that same one line, and the pick goes on."
ISSUE_ANSWER_PASSED_OVER_OUTPUT = "Before the ruling: § Input's one line when the pick passed over an item, then the question, and nothing else."
ISSUE_ANSWER_RULING_PAIRS = "A `## Ruling` comment answers the earliest unanswered `## Question` before it"
ISSUE_ANSWER_EARLIEST_UNANSWERED = "the question is the earliest `## Question` still unanswered"
ISSUE_ANSWER_LABEL_EDIT = "`gh issue edit <N> --remove-label question --repo <owner/name>`"
ISSUE_ANSWER_NONE_LEFT = "With no `## Question` on the item left unanswered"
ISSUE_ANSWER_ANY_LEFT = "With any left, the item keeps `question`"
ISSUE_ANSWER_ONE_ITEM = "One item per message"
ISSUE_ANSWER_RESTART = "names what restarts"
ISSUE_ANSWER_RESTART_ROUTES = (
    "nothing for the ready question `issue-triage` § Ready files when the ruling is ready",
    "`issue-triage` on the item for every other ruling on a question `issue-triage` filed, for one `issue-write` filed and for one `deliver § Intake` filed",
    "`issue-next` for one `deliver` filed",
)
ISSUE_ANSWER_READY_RULING = (
    "the ready question `issue-triage` § Ready files",
    "`gh issue edit <N> --add-label ready --remove-label question --repo <owner/name>`",
    "`ready` unless the item carries `paused`",
)
ISSUE_TRIAGE_THIN_TEXT_REFUSE = "`issue-write` § Refuse"
ISSUE_TRIAGE_THIN_TEXT_FILED = "§ Apply's question row"
ISSUE_TRIAGE_NO_ASK = "Nothing here asks the user."
ISSUE_TRIAGE_RUN_ORDER = (
    "§ Draft for a thin item, then § Duplicate, then § Done",
    "an item closed there takes nothing further",
    "then § Critique, which runs again after every edit until it returns `ACCEPTED`, a finding is held or the item is split",
    "then § Ready",
)
ISSUE_TRIAGE_EXITS = "What leaves this skill is a closed item, one split and waiting on its pieces, or an open one under `question`"
ISSUE_TRIAGE_HELD_CLASSES = (
    "a change to the § Goal or the scope",
    "a sentence `issue-write` § Refuse would name as missing",
    "a choice `rules/decisions.md` does not settle",
    "a finding § Critique's stop rule trips on — a disagreement that survived two critique runs, or a defect two runs in a row each traced to the previous run's edit",
)
ISSUE_TRIAGE_HELD_FILED = "filed through `issue-question` with a recommender run"
ISSUE_TRIAGE_HELD_ENDS_RUN = "A held finding ends the run once every other finding is applied; the restart carries the rulings in § Critique's `Decisions made:` and runs the critique again."
ISSUE_TRIAGE_SPLIT_ENDS_RUN = "A split ends the run too, the original waiting on its pieces per `issue-next` § Skip."
ISSUE_TRIAGE_DRAFT_APPLIED = ("Both are applied before anything else runs", "`gh issue edit <N> --add-label <label> --add-label <label>`", "`gh issue edit <N> --body-file <path>`")
ISSUE_TRIAGE_CRITIQUE_CHANGE_SET_BRIEF = "the `## Brief` § Ready drafts from it"
ISSUE_TRIAGE_CRITIQUE_BRIEF_LINE = "the `## Brief` fills every `rules/brief.md` field from the item's state"
ISSUE_TRIAGE_CRITIQUE_DECISIONS = "Decisions made:  the item's rulings, as `issue-next` § Output fills the field"
ISSUE_TRIAGE_FIX_LIST_APPLIED = (
    "the fix list is applied as one body edit, `gh issue edit <N> --body-file <path>`",
    "a line against the `## Brief` applied to § Ready's redraft of it instead",
    "the critique runs again on the edited state",
)
ISSUE_TRIAGE_FIX_LIST_HELD_LINE = "one of the four § State holds — held, its line left out of the edit"
ISSUE_TRIAGE_BLOCKED_HELD = "`BLOCKED` says the item's own text cannot fill an acceptance line above: that gap is held."
ISSUE_TRIAGE_STOP_RULE = (
    "Stop rule, the circuit breaker `skills/deliver/references/review-loop.md` gives",
    "a finding the previous run also raised is a disagreement that survived two rounds, held",
    "two runs in a row each finding a defect the previous run's edit introduced trip it, those findings held",
    "No other bound: the loop runs until the verdict is `ACCEPTED`, a finding is held or the item is split.",
)
ISSUE_TRIAGE_RULING_SETTLES = "A finding a ruling on the item settles is applied as the ruling says, never held."
ISSUE_TRIAGE_EMPTY_FIX_LIST = "A `NOT ACCEPTED` that splits nothing, closes nothing, holds nothing and leaves no line to apply counts as `ACCEPTED`, with no body edit."
ISSUE_TRIAGE_EVIDENCE_FILE = "`issue-<N>-<purpose>.md`"
ISSUE_TRIAGE_EVIDENCE_POST = "`gh issue comment <N> --body-file <scratchpad file>`"
ISSUE_TRIAGE_EVIDENCE_LATEST = "under each heading the latest comment is the current one"
ISSUE_TRIAGE_EVIDENCE_BULLETS = ("- `## Brief` —", "- `## Plan` —", "- `## Design` —")
ISSUE_TRIAGE_BRIEF_COMMENT = (
    "the ten fields `rules/brief.md` defines, in its shape",
    "the six `issue-next` § Output fills",
    "Files in scope, Verification, Invariant and Instructions",
    "every path repo-relative",
    "Drafted before each critique run from the state as it then stands",
    "posted when the critique returns `ACCEPTED`",
)
ISSUE_TRIAGE_PLAN_COMMENT = ("`tier: complex`", "when the item carries none", "one line per step in order, each with the invariant it keeps", "`plan-phases`")
ISSUE_TRIAGE_DESIGN_COMMENT = ("changes a public surface and carries none", "`design-surface` runs on the item, and its § Exit posts the comment")
ISSUE_TRIAGE_READY_QUESTION = "`Is #N ready to deliver as briefed?`"
ISSUE_TRIAGE_READY_QUESTION_GATE = (
    "filed through `issue-question` only when every comment above is posted and no `## Question` on the item is unanswered",
    "its recommendation is ready, linking the `## Brief`, `## Plan` and `## Design` comments the item carries",
    "`issue-question` runs no recommender for it",
    "The ruling is `issue-answer`'s: ready sets `ready` there, and any other ruling restarts this skill with it.",
)
ISSUE_TRIAGE_APPLY_PRECEDENCE = "by precedence — done, duplicate, split, question, ready"
ISSUE_TRIAGE_APPLY_ROWS = ("- done —", "- duplicate —", "- split —", "- question —", "- ready —")
ISSUE_TRIAGE_ROWS_ADD_NO_LABEL = "The question row and the ready row add no label themselves"
ISSUE_TRIAGE_FILING_LABEL = "the item leaves the queue under `question`, the label that filing adds"
ISSUE_TRIAGE_READY_EXAMPLE_ROW = "| `<N>` | ready | — | — | `## Brief`, `## Question` | — |"
ISSUE_TRIAGE_READY_ROW = ("the ready question, filed through `issue-question` as § Ready says", "`ready` itself is `issue-answer`'s to add")
ISSUE_TRIAGE_ROWS_TAKE_READY_OFF = "Every body edit — the draft, a fix list, the split's § Related — takes `ready` off an item that carries it: `gh issue edit <N> --remove-label ready`."
ISSUE_TRIAGE_SPLIT_PIECES = ("created through `issue-write` from § Create step 2 on", "one `Depends on` line per piece")
ISSUE_TRIAGE_DUPLICATE_CLOSE = "`gh issue close <N> --duplicate-of <M> --comment <text>`"
ISSUE_TRIAGE_DUPLICATE_NO_LABEL = "no label"
DELIVER_DEVIATION_FILED = "when the ruling is the user's, file it through `issue-question` on the item, pause the item and continue the loop with the next"
DELIVER_RULING_PREMISE = "a factual premise inside a ruling goes through `/verify-claim` before it enters a brief"
DELIVER_OPEN_ENTRY_UNCOMMITTED = "An item with an open ledger entry is not committed to the working branch until the user rules"
DELIVER_SESSION_LIMIT_PAUSES = "On a session-limit error stop dispatching, pause each item in flight, state the checkpoint"
DELIVER_PAUSE_TRIGGERS = ("a deviation filed through `issue-question`", "a breaker trip that ends the run (`references/review-loop.md`)", "a session-limit stop")
DELIVER_PAUSE_APPLIES_TO = "applies to an item with a tracker reference and changes in the tree"
DELIVER_PAUSE_EACH_COMMAND_ALONE = "Each command runs on its own:"
DELIVER_PAUSED_SUBJECT = "chore(paused): paused work for #<N>"
DELIVER_PAUSED_FOOTER = "Refs #<N>"
DELIVER_PAUSE_STEPS = (
    "`git switch -c paused/<N>-<k>`, k the item's count of `## Paused` comments plus one",
    "`git add -- <paths>`, the item's paths by name",
    "`git commit -F - -- <paths> <<'EOF' … EOF`",
    f"`{DELIVER_PAUSED_SUBJECT}`",
    "a body naming the working branch, what is done and the next step",
    f"`{DELIVER_PAUSED_FOOTER}`",
    "`git push origin paused/<N>-<k>`",
    "`git switch <working branch>`",
    "a `## Paused` comment on the item — the paused branch, the working branch, what is done and the next step —",
    "`gh issue comment <N> --body-file <scratchpad file>`",
    "`gh issue edit <N> --add-label paused --remove-label ready`",
)
DELIVER_RESUME_AFTER_INTAKE = "A `paused` item resumes after § Intake's check"
DELIVER_RESUME_STEPS = (
    "read its latest `## Paused` comment",
    "`git fetch origin paused/<N>-<k>:paused/<N>-<k>` when the branch is not local",
    "on the session's working branch `git cherry-pick --no-commit paused/<N>-<k>`",
    "a conflicted path keeps its markers",
    "`paused` stays until the item closes",
    "a later pause cuts `paused/<N>-<k+1>`",
)
DELIVER_PAUSED_DELETE_AFTER_CLOSE = "Once the item is closed,"
DELIVER_PAUSED_DELETE = (
    "`git branch -D paused/<N>-<k>` for each branch `git branch --list 'paused/<N>-*'` prints",
    "`git push origin --delete paused/<N>-<k>` for each `git ls-remote origin 'refs/heads/paused/<N>-*'` prints",
)
PAUSE_PLACEHOLDERS = (("<N>", "12"), ("<k>", "1"), ("<paths>", "a"), ("<working branch>", "main"), ("<scratchpad file>", "paused.md"))
CLAUDE_MD_TRACKER_QUESTION = "A question on a tracker item is filed through `issue-question` and reported in one line; one with no item is asked inline as above."
QUESTION_EXAMPLE_PER_OPTION = "a concrete example and its cost"
QUESTION_CODE_WHEN = "an option that changes code or a file"
QUESTION_REAL_TEXT_IN_CODE = "the real text today and the real text proposed, each in a code block"
QUESTION_ONE_LINE = "A question a cited specification section settles, or whose fix is obvious, is one line instead: the bare, fully qualified reference as `rules/writing.md` gives it where a section settles it, and the recommendation, nothing else."
ISSUE_ANSWER_PRESENT_FORM = "in the form `claude/CLAUDE.md` § Questions gives — the one line or the full one, as the question calls for — then stop"
DECISIONS_DOUBT_GATE = "or it is in doubt which one does"
DECISIONS_DOUBT_RULE = "in doubt, the specification's reading wins"
ISSUE_NEXT_DECISIONS_FROM_RULINGS = "in comment order, or `none`"
ISSUE_NEXT_EVENT_LOG = (
    "`gh issue view <N> --json body,comments` reads it as an event log",
    "the body is the starting state, and each comment applies in order",
    "a later one overriding what it names in the body or an earlier comment",
    "Every field carries the state after the last comment",
)
ISSUE_NEXT_EVIDENCE_OVERRIDES_NOTHING = "A `## Brief`, `## Plan` or `## Design` comment overrides nothing: it is evidence the item carries, read as itself."
ISSUE_NEXT_EVIDENCE_THE_ITEM_CARRIES = "evidence the item carries"
ISSUE_NEXT_SKIP_READS_THE_STATE = "read as § Output reads it"
ISSUE_TRIAGE_VIEW = "`gh issue view <N> --json number,title,labels,body,comments`"
ISSUE_TRIAGE_STATE_CITES_ISSUE_NEXT = "its state is its body and comments read as `issue-next` § Output reads them"
ISSUE_TRIAGE_THIN_BY_STATE = "is missing from its state"
ISSUE_TRIAGE_CRITIQUE_STATE = "the item's state verbatim"
ISSUE_TRIAGE_PUSH_CHECK = "git branch -r --contains"
ISSUE_TRIAGE_DONE_NO_COMMIT = "When no verdict cites a commit, the item is not done either: it stays open"
ISSUE_TRIAGE_DONE_ORDER = (
    "`VERIFIED` for every line",
    "`git branch -r --contains <hash>` on each commit the verdicts cite, against the remote-tracking refs as they stand, with no fetch",
    "A branch printed for every commit is done: the item closes with a comment carrying those commits",
    "Nothing printed for one of them is not done: the item stays open, each commit without a branch unpushed",
)
ISSUE_TRIAGE_DONE_ROW_CLOSE = ("each commit `<hash>` § Done's verdicts cite", "`gh issue close <N> --comment <text>`")
ISSUE_TRIAGE_OUTPUT_UNVERIFIED = "the acceptance lines no verdict returned `VERIFIED` for"
ISSUE_TRIAGE_OUTPUT_UNPUSHED = "the commits § Done found on no remote branch, each named as unpushed, or that no verdict cited a commit"
ISSUE_TRIAGE_SECTIONS = ("Input", "State", "Draft", "Duplicate", "Critique", "Done", "Ready", "Apply", "Output")
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


def questions_paragraph():
    return next(p for p in read(CLAUDE / "CLAUDE.md").split("\n\n") if p.startswith("**Questions.**"))


def sentence_count(text):
    return len(re.findall(r'[.!?]["\u201d)]*(?=\s|$)', text.strip()))


def gh_labels(text):
    arguments = [*GH_LABEL_ARGUMENT.finditer(text)]
    for call in GH_LABEL_SHORTHAND_CALL.findall(text):
        arguments += GH_LABEL_SHORTHAND_ARGUMENT.finditer(call)
    labels = []
    for argument in arguments:
        for name in filter(None, argument.groups()):
            labels += name.split(",") if argument.group().startswith("-") else [name]
    return labels


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

    def test_issue_writer_holds_agent_and_skill_and_is_dispatched_by_the_chat_in_the_background_one_per_discussion(self):
        fields, _ = agent_docs()["issue-writer"]
        self.assertEqual(fields["tools"], ISSUE_WRITER_TOOLS)
        self.assertIn(ISSUE_WRITER_DISPATCH, fields["description"])

    def test_issue_writer_creates_in_dependency_order_waits_past_each_turn_boundary_for_every_verdict_and_filed_question_and_returns_one_line_per_item(self):
        _, body = agent_docs()["issue-writer"]
        text = re.sub(r"\s+", " ", body)
        for passage in ISSUE_WRITER_BODY:
            with self.subTest(passage=passage):
                self.assertIn(passage, text)
        offsets = [text.index(passage) for passage in ISSUE_WRITER_BODY]
        self.assertEqual(offsets, sorted(offsets))

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

    def test_the_three_researcher_agents_preload_the_research_skill_share_one_body_and_differ_in_model(self):
        docs = agent_docs()
        researchers = [docs[stem] for stem in sorted(RESEARCHER_AGENTS)]
        for stem, (fields, _) in zip(sorted(RESEARCHER_AGENTS), researchers):
            with self.subTest(agent=stem):
                self.assertEqual(fields["skills"], ["research"])
        self.assertEqual(len({fields["model"] for fields, _ in researchers}), len(RESEARCHER_AGENTS))
        self.assertEqual(len({fields["tools"] for fields, _ in researchers}), 1)
        self.assertEqual(len({body for _, body in researchers}), 1)

    def test_each_researcher_description_says_the_chat_dispatches_it_per_the_research_routing(self):
        docs = agent_docs()
        for stem in RESEARCHER_AGENTS:
            with self.subTest(agent=stem):
                self.assertIn(RESEARCHER_DISPATCH, docs[stem][0]["description"])

    def test_each_researcher_description_names_its_research_routing_lane_and_not_the_other_lane_kind(self):
        docs = agent_docs()
        for row in RESEARCH_ROUTING_ROWS:
            _, lane, stem = (cell.strip().strip("`") for cell in row.strip("|").split("|"))
            with self.subTest(agent=stem):
                description = docs[stem][0]["description"]
                self.assertIn(lane, description)
                for kind in RESEARCH_LANE_KINDS:
                    if not lane.startswith(kind):
                        self.assertNotIn(kind, description)

    def test_an_agent_description_says_not_invoked_directly_only_when_a_skill_dispatches_it(self):
        skills = set(skill_docs())
        for stem, (fields, _) in agent_docs().items():
            if NOT_INVOKED_DIRECTLY in fields["description"]:
                with self.subTest(agent=stem):
                    dispatch = DISPATCHED_THROUGH_A_SKILL.search(fields["description"])
                    self.assertIsNotNone(dispatch)
                    self.assertIn(dispatch.group(1), skills)

    def test_verify_claim_and_the_verifier_send_broad_source_gathering_to_the_research_skill(self):
        for door, text in (("verify-claim", skill_docs()["verify-claim"][0]["description"]), ("verifier", agent_docs()["verifier"][1])):
            with self.subTest(door=door):
                self.assertIn(BROAD_GATHERING_TO_RESEARCH, text)

    def test_no_fork_target_preloads_a_skill(self):
        docs = agent_docs()
        targets = {fields["agent"] for fields, _ in skill_docs().values() if fields.get("context") == "fork"}
        self.assertTrue(targets)
        for stem in targets:
            with self.subTest(agent=stem):
                self.assertNotIn("skills", docs[stem][0])


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

    def test_in_doubt_which_option_meets_the_requirement_the_first_tie_break_decides_and_the_specifications_reading_wins(self):
        text = read(RULES / "decisions.md")
        self.assertIn(DECISIONS_DOUBT_GATE, re.sub(r"\s+", " ", text))
        first = next(line for line in text.splitlines() if line.startswith("1. "))
        self.assertIn(DECISION_TIE_BREAKS[0], first)
        self.assertIn(DECISIONS_DOUBT_RULE, first)

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

    def test_each_commit_is_followed_by_a_push_of_its_branch_stated_once(self):
        text = re.sub(r"\s+", " ", read(RULES / "git.md"))
        self.assertEqual(text.count(GIT_PUSH_AFTER_COMMIT), 1)

    def test_an_item_is_done_when_a_remote_branch_carries_the_commits_that_land_its_change_sets_merged_or_not_stated_once(self):
        text = re.sub(r"\s+", " ", read(RULES / "git.md"))
        self.assertEqual(text.count(GIT_DONE_ON_A_REMOTE_BRANCH), 1)

    def test_only_a_push_to_main_asks_through_the_permission_prompt_stated_once_in_the_ask_bullet_before_its_item_clauses(self):
        text = re.sub(r"\s+", " ", read(RULES / "git.md"))
        self.assertEqual(text.count(GIT_PUSH_ASKS_ONLY_ON_MAIN), 1)
        bullets = [re.sub(r"\s+", " ", bullet).strip() for bullet in read(RULES / "git.md").split("\n- ")]
        bullet = next(bullet for bullet in bullets if bullet.startswith("Ask first"))
        self.assertIn(GIT_PUSH_ASKS_ONLY_ON_MAIN, bullet)
        self.assertLess(bullet.index(GIT_PUSH_ASKS_ONLY_ON_MAIN), bullet.index(GIT_ITEM_FROM_A_DISCUSSION))

    def test_paused_work_is_committed_and_pushed_only_to_its_paused_branch_and_reaches_the_working_branch_uncommitted(self):
        bullets = [re.sub(r"\s+", " ", bullet).strip() for bullet in read(RULES / "git.md").split("\n- ")]
        bullet = next(bullet for bullet in bullets if CHANGE_SET_PER_COMMIT in bullet)
        self.assertTrue(bullet.endswith(f"{GIT_PAUSED_WORK_EXCEPTION}."), bullet)

    def test_an_item_that_comes_out_of_a_discussion_with_the_user_is_created_on_that_discussion_and_none_automatically(self):
        bullets = [re.sub(r"\s+", " ", bullet).strip() for bullet in read(RULES / "git.md").split("\n- ")]
        bullet = next(bullet for bullet in bullets if bullet.startswith("Ask first"))
        self.assertTrue(bullet.endswith(GIT_ITEM_FROM_A_DISCUSSION), bullet)


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

    def test_research_row_and_description_both_run_the_lane_in_a_researcher_agent(self):
        body = read(CLAUDE / "CLAUDE.md")
        row = next(line for line in body.splitlines() if line.startswith("| `research` |"))
        self.assertIn(RESEARCH_ROW_AGENT, row)
        fields, _ = skill_docs()["research"]
        self.assertIn(RESEARCH_DESCRIPTION_AGENT, fields["description"])

    def test_issue_write_row_and_description_both_fire_when_a_discussion_with_the_user_yields_items_to_add(self):
        body = read(CLAUDE / "CLAUDE.md")
        row = next(line for line in body.splitlines() if line.startswith("| `issue-write` |"))
        self.assertTrue(row.startswith(f"| `issue-write` | {ISSUE_WRITE_ROW_TRIGGER} — "), row)
        fields, _ = skill_docs()["issue-write"]
        self.assertIn(ISSUE_WRITE_DESCRIPTION_TRIGGER, fields["description"])

    def test_issue_write_row_sends_the_discussion_to_one_background_issue_writer_with_the_users_words_verbatim_and_the_chat_carries_on_relays_and_triages_unasked_inside_the_claude_only_block(self):
        body = read(CLAUDE / "CLAUDE.md")
        row = next(line for line in body.splitlines() if line.startswith("| `issue-write` |"))
        for passage in ISSUE_WRITE_ROW_INTAKE:
            with self.subTest(passage=passage):
                self.assertIn(passage, row)
        offsets = [row.index(passage) for passage in ISSUE_WRITE_ROW_INTAKE]
        self.assertEqual(offsets, sorted(offsets))
        self.assertNotIn("issue-writer", render_agents_md.render(CLAUDE / "CLAUDE.md", RULES))

    def test_design_surface_row_and_description_both_name_the_run_with_the_user_before_code_and_the_run_inside_issue_triage_without_them(self):
        body = read(CLAUDE / "CLAUDE.md")
        row = next(line for line in body.splitlines() if line.startswith("| `design-surface` |"))
        self.assertIn(DESIGN_ROW_MODES, row)
        fields, _ = skill_docs()["design-surface"]
        self.assertIn(DESIGN_DESCRIPTION_MODES, fields["description"])

    def test_a_question_on_a_tracker_item_is_filed_through_issue_question_and_one_without_is_asked_inline(self):
        self.assertIn(CLAUDE_MD_TRACKER_QUESTION, re.sub(r"\s+", " ", read(CLAUDE / "CLAUDE.md")))

    def test_a_question_a_cited_specification_section_settles_or_whose_fix_is_obvious_is_one_line_in_the_questions_paragraph_inside_the_claude_only_block(self):
        paragraph = re.sub(r"\s+", " ", questions_paragraph())
        rendered = re.sub(r"\s+", " ", render_agents_md.render(CLAUDE / "CLAUDE.md", RULES))
        self.assertIn(QUESTION_ONE_LINE, paragraph)
        self.assertNotIn(QUESTION_ONE_LINE, rendered)

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

    def test_config_names_no_marketplace(self):
        self.assertEqual({str(path.relative_to(REPO)) for path, text in text_files(CLAUDE) if "marketplace" in text.casefold()}, set())

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

    def test_issue_write_labels_priority_bullet_offers_priority_blocker_then_high_medium_or_low_as_the_tracker_label_descriptions_decide(self):
        _, body = skill_docs()["issue-write"]
        self.assertIn(ISSUE_WRITE_PRIORITY_BULLET, section(body, "Labels").splitlines())

    def test_issue_write_labels_status_bullet_hands_out_paused_after_blocker_priority_items_and_before_the_rest(self):
        _, body = skill_docs()["issue-write"]
        self.assertIn(ISSUE_WRITE_STATUS_BULLET, section(body, "Labels").splitlines())

    def test_issue_write_labels_status_line_names_ready_then_paused_one_at_most_on_an_open_item_and_neither_for_the_backlog(self):
        _, body = skill_docs()["issue-write"]
        line = next(l for l in section(body, "Labels").splitlines() if l.startswith(ISSUE_WRITE_STATUS_LINE))
        offsets = [line.index(f"`{label}`") for label in STATUS_LABELS]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn(ISSUE_WRITE_STATUS_AT_MOST_ONE, line)

    def test_issue_write_labels_holds_line_names_the_hold_labels_in_order_and_no_other(self):
        _, body = skill_docs()["issue-write"]
        line = next(l for l in section(body, "Labels").splitlines() if l.startswith(ISSUE_WRITE_HOLDS_LINE))
        self.assertEqual(re.findall(r"`([^`]+)`", line), list(HOLD_LABELS))

    def test_every_label_a_gh_call_in_the_payload_names_is_a_repository_label(self):
        for path in payload_files():
            for label in gh_labels(read(path)):
                with self.subTest(file=str(path.relative_to(REPO)), label=label):
                    self.assertIn(label, REPOSITORY_LABELS)

    def test_the_label_argument_pattern_reads_every_label_form_gh_documents(self):
        forms = {
            '`gh issue edit <N> --add-label "priority: high" --remove-label ready`': ["priority: high", "ready"],
            "`gh issue list --label=question`": ["question"],
            '`gh issue create --label bug --label "help wanted"`': ["bug", "help wanted"],
            '`gh pr create --label "bug,help wanted"`': ["bug", "help wanted"],
            "`gh issue edit <N> --add-label=bug --remove-label=paused`": ["bug", "paused"],
            '`gh issue edit <N> --add-label "bug,help wanted" --remove-label paused`': ["bug", "help wanted", "paused"],
            '`gh pr edit <N> --add-label bug,ready --remove-label "priority: low"`': ["bug", "priority: low", "ready"],
            '`gh discussion edit <N> --add-label bug --remove-label "help wanted"`': ["bug", "help wanted"],
            "`gh search issues --label question --repo <owner/name>`": ["question"],
            '`gh search prs --label "bug,ready"`': ["bug", "ready"],
            "`gh issue list -l question --repo <owner/name>`": ["question"],
            "`gh issue ls -l question`": ["question"],
            '`gh issue create -l bug -l "help wanted"`': ["bug", "help wanted"],
            '`gh pr create -l "bug,help wanted"`': ["bug", "help wanted"],
            "`gh issue new -l paused`": ["paused"],
            "`gh pr ls -l ready`": ["ready"],
            "`gh pr list -l ready`": ["ready"],
            "`gh pr new -l paused`": ["paused"],
            '`gh discussion create -l "bug,help wanted"`': ["bug", "help wanted"],
            "`gh discussion list -l question --repo <owner/name>`": ["question"],
            "`gh discussion ls -l ready`": ["ready"],
            '`gh label create question --description "<description>"`': ["question"],
            '`gh label create "bug,ready"`': ["bug,ready"],
            "`gh label delete wontfix --yes`": ["wontfix"],
            '`gh label edit question --description "<description>" --repo <owner/name>`': ["question"],
            '`gh label edit "tier: trivial" --name parked`': ["parked", "tier: trivial"],
            '`gh label edit parked --description "<description>" --name "help wanted"`': ["help wanted", "parked"],
            "`gh label edit wontfix -n parked`": ["parked", "wontfix"],
            '`gh label edit wontfix --name="help wanted"`': ["help wanted", "wontfix"],
            "`git diff --cached --name-only`": [],
            "`gh run download --name parked`": [],
            "`gh run download -n parked`": [],
            "`wc -l parked`": [],
            "`gh issue develop -l 87`": [],
            "`gh issue develop <N> -n parked`": [],
            "`gh codespace create -l WestEurope`": [],
            "`gh repo create <name> -l mit`": [],
            "`gh repo list -l python`": [],
            "`gh discussion new -l ready`": [],
            "`gh release create <tag> -n parked`": [],
            "`gh label list -S parked`": [],
            "`gh search issues --no-label ready`": [],
            "`gh search repos --good-first-issues 1`": [],
        }
        for text, labels in forms.items():
            with self.subTest(text=text):
                self.assertEqual(sorted(gh_labels(text)), sorted(labels))

    def test_issue_write_create_carries_each_relation_mutation_once(self):
        _, body = skill_docs()["issue-write"]
        create = section(body, "Create")
        for mutation in RELATION_MUTATIONS:
            with self.subTest(mutation=mutation):
                self.assertEqual(body.count(mutation), 1)
                self.assertIn(mutation, create)

    def test_issue_write_input_takes_an_item_from_a_discussion_with_the_user_and_raises_a_finding_made_during_work_rather_than_filing_it(self):
        _, body = skill_docs()["issue-write"]
        inputs = re.sub(r"\s+", " ", section(body, "Input"))
        for passage in (ISSUE_WRITE_INPUT_FROM_A_DISCUSSION, ISSUE_WRITE_FINDING_RAISED_NOT_FILED):
            with self.subTest(passage=passage):
                self.assertIn(passage, inputs)
        self.assertLess(inputs.index(ISSUE_WRITE_INPUT_FROM_A_DISCUSSION), inputs.index(ISSUE_WRITE_FINDING_RAISED_NOT_FILED))

    def test_issue_write_input_brings_the_rest_of_the_set_the_discussion_yields_for_check(self):
        _, body = skill_docs()["issue-write"]
        self.assertIn(ISSUE_WRITE_INPUT_THE_SET, re.sub(r"\s+", " ", section(body, "Input")))

    def test_issue_write_checks_every_item_refuse_lets_through_before_create_and_creates_nothing_for_one_a_check_stops(self):
        _, body = skill_docs()["issue-write"]
        for heading in ISSUE_WRITE_SECTIONS:
            with self.subTest(heading=heading):
                self.assertEqual(body.count(f"\n## {heading}\n"), 1)
        offsets = [body.index(f"\n## {heading}\n") for heading in ISSUE_WRITE_SECTIONS]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn(ISSUE_WRITE_CHECK_GATE, section(body, "Check"))

    def test_issue_write_check_stops_an_open_duplicate_a_goal_resting_on_a_disproven_claim_and_a_goal_the_tree_satisfies(self):
        _, body = skill_docs()["issue-write"]
        bullets = [line for line in section(body, "Check").splitlines() if line.startswith("- ")]
        self.assertEqual([line[: line.index(":") + 1] for line in bullets], list(ISSUE_WRITE_CHECK_BULLETS))
        for bullet, (label, passages) in zip(bullets, ISSUE_WRITE_CHECK_BULLETS.items()):
            for passage in passages:
                with self.subTest(bullet=label, passage=passage):
                    self.assertIn(passage, bullet)
            with self.subTest(bullet=label, order=True):
                offsets = [bullet.index(passage) for passage in passages]
                self.assertEqual(offsets, sorted(offsets))

    def test_issue_write_check_cites_the_triage_duplicate_test_rather_than_restating_it_and_leaves_the_critique_and_acceptance_verdicts_to_triage(self):
        docs = skill_docs()
        _, body = docs["issue-write"]
        self.assertIn(ISSUE_WRITE_CHECK_LEAVES_TRIAGE, section(body, "Check"))
        self.assertIn(ISSUE_TRIAGE_SAMENESS_TEST, section(docs["issue-triage"][1], "Duplicate"))
        for restated in (ISSUE_TRIAGE_SAMENESS_TEST, "gh issue list"):
            with self.subTest(restated=restated):
                self.assertNotIn(restated, body)

    def test_issue_write_check_lets_a_dependent_follow_its_blocker_the_duplicates_open_match_standing_in_and_any_other_stop_leaving_it_uncreated(self):
        _, body = skill_docs()["issue-write"]
        check = section(body, "Check")
        self.assertIn(ISSUE_WRITE_CHECK_DEPENDENTS, check)
        self.assertLess(check.index("\n- Done:"), check.index(ISSUE_WRITE_CHECK_DEPENDENTS))
        self.assertLess(check.index(ISSUE_WRITE_CHECK_DEPENDENTS), check.index(ISSUE_WRITE_CHECK_LEAVES_TRIAGE))

    def test_issue_triage_critique_judges_each_why_claim_so_an_unverifiable_one_issue_write_check_lets_through_is_judged_there(self):
        self.assertIn(ISSUE_TRIAGE_CRITIQUE_WHY_LINE, section(skill_docs()["issue-triage"][1], "Critique"))

    def test_issue_write_output_returns_the_refuse_question_or_what_check_stopped_when_nothing_is_created(self):
        _, body = skill_docs()["issue-write"]
        self.assertIn(ISSUE_WRITE_OUTPUT_STOPPED, section(body, "Output"))

    def test_issue_write_create_takes_the_discussion_with_the_user_as_the_word_for_every_item_keeps_the_steps_triage_cites_in_number_and_posts_a_settled_plan_for_a_complex_item_last(self):
        _, body = skill_docs()["issue-write"]
        steps = [line for line in section(body, "Create").splitlines() if re.match(r"\d+\. ", line)]
        self.assertEqual(len(steps), len(ISSUE_WRITE_CREATE_STEPS))
        for step, prefix in zip(steps, ISSUE_WRITE_CREATE_STEPS):
            with self.subTest(step=prefix):
                self.assertTrue(step.startswith(prefix), step)
        self.assertEqual(steps[0], ISSUE_WRITE_CREATE_STEP_1)
        plan = steps[-1]
        for passage in ISSUE_WRITE_PLAN_STEP:
            with self.subTest(passage=passage):
                self.assertIn(passage, plan)
        offsets = [plan.index(passage) for passage in ISSUE_WRITE_PLAN_STEP]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_next_skip_names_the_hold_labels_in_order_and_no_other_holds_an_item_whatever_its_status_and_reports_the_label_that_skipped_it(self):
        _, body = skill_docs()["issue-next"]
        line = next(l for l in section(body, "Skip").splitlines() if ISSUE_NEXT_HOLD_LABELS in l)
        self.assertEqual(re.findall(r"`([^`]+)`", line), list(HOLD_LABELS))
        self.assertIn(ISSUE_NEXT_HELD_WHATEVER_STATUS, line)
        self.assertIn(ISSUE_NEXT_HOLD_REPORTED, line)

    def test_issue_next_description_first_sentence_orders_priority_blocker_first_then_by_status_then_urgency_and_blocked_by_nothing_open(self):
        fields, _ = skill_docs()["issue-next"]
        self.assertEqual(re.split(r"(?<=[.!?])\s+", fields["description"])[0], ISSUE_NEXT_DESCRIPTION_ORDER)

    def test_issue_next_order_ranks_priority_blocker_then_high_then_medium_then_low_then_unlabelled(self):
        _, body = skill_docs()["issue-next"]
        self.assertIn(ISSUE_NEXT_PRIORITY_ORDER, section(body, "Order"))

    def test_issue_next_order_walks_blocker_priority_items_then_paused_then_ready_then_the_backlog_each_in_urgency_order_and_stops_only_when_every_item_is_held(self):
        _, body = skill_docs()["issue-next"]
        order = re.sub(r"\s+", " ", section(body, "Order"))
        passages = (ISSUE_NEXT_LAST_SORT_KEY, ISSUE_NEXT_GROUPS, ISSUE_NEXT_WALK_THE_GROUPS, ISSUE_NEXT_EVERY_ITEM_HELD)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, order)
        offsets = [order.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_next_flags_a_backlog_winner_as_one_to_triage_not_to_deliver(self):
        _, body = skill_docs()["issue-next"]
        self.assertIn(ISSUE_NEXT_BACKLOG_TO_TRIAGE, re.sub(r"\s+", " ", section(body, "Output")))

    def test_issue_next_output_reports_each_item_skipped_above_the_winner_with_the_open_number_or_the_label_that_skipped_it(self):
        _, body = skill_docs()["issue-next"]
        self.assertIn(ISSUE_NEXT_SKIPPED_REPORTED, re.sub(r"\s+", " ", section(body, "Output")))

    def test_issue_next_skip_reads_blockers_and_pieces_from_the_relations(self):
        _, body = skill_docs()["issue-next"]
        skip = section(body, "Skip")
        for field in ("blockedBy", "subIssues"):
            with self.subTest(field=field):
                self.assertIn(field, skip)

    def test_issue_next_output_names_every_brief_field_it_fills(self):
        _, body = skill_docs()["issue-next"]
        output = section(body, "Output")
        for label in ISSUE_NEXT_BRIEF_FIELDS:
            with self.subTest(label=label):
                self.assertIn(label, output)

    def test_issue_next_fills_decisions_made_from_the_ruling_comments_in_comment_order(self):
        _, body = skill_docs()["issue-next"]
        output = section(body, "Output")
        self.assertIn(ISSUE_NEXT_DECISIONS_FROM_RULINGS, output)
        self.assertLess(output.index("Decisions made:"), output.index(ISSUE_NEXT_DECISIONS_FROM_RULINGS))

    def test_issue_next_fills_every_brief_field_from_the_body_and_each_comment_in_order_a_later_one_overriding(self):
        _, body = skill_docs()["issue-next"]
        output = section(body, "Output")
        for passage in ISSUE_NEXT_EVENT_LOG:
            with self.subTest(passage=passage):
                self.assertIn(passage, output)
        offsets = [output.index(passage) for passage in ISSUE_NEXT_EVENT_LOG]
        self.assertEqual(offsets, sorted(offsets))
        self.assertLess(offsets[-1], output.index("```text"))
        self.assertEqual(body.count("gh issue view"), 1)
        blocked = next(line for line in section(body, "Skip").splitlines() if "`BLOCKED`" in line)
        self.assertIn(ISSUE_NEXT_SKIP_READS_THE_STATE, blocked)

    def test_issue_next_reads_a_brief_plan_or_design_comment_as_evidence_the_item_carries_that_overrides_nothing_in_the_event_log(self):
        docs = skill_docs()
        paragraph = next(p for p in section(docs["issue-next"][1], "Output").split("\n\n") if ISSUE_NEXT_EVENT_LOG[0] in p)
        self.assertIn(ISSUE_NEXT_EVIDENCE_OVERRIDES_NOTHING, paragraph)
        self.assertLess(paragraph.index(ISSUE_NEXT_EVENT_LOG[2]), paragraph.index(ISSUE_NEXT_EVIDENCE_OVERRIDES_NOTHING))
        sentence = next(s for s in paragraph.split(". ") if "overrides nothing" in s)
        bullets = [line for line in section(docs["issue-triage"][1], "Ready").splitlines() if line.startswith("- ")]
        for heading in (line[2 : line.index(" —")] for line in bullets):
            with self.subTest(heading=heading):
                self.assertIn(heading, sentence)
        self.assertIn(ISSUE_NEXT_EVIDENCE_THE_ITEM_CARRIES, sentence)

    def test_issue_next_hands_a_ready_or_paused_winner_its_latest_brief_with_later_rulings_under_decisions_made_and_derives_the_backlog_after_the_event_log_read(self):
        _, body = skill_docs()["issue-next"]
        output = re.sub(r"\s+", " ", section(body, "Output"))
        passages = (ISSUE_NEXT_EVENT_LOG[-1], ISSUE_NEXT_READY_LEAVES_AS_ITS_BRIEF, ISSUE_NEXT_NO_BRIEF_LEAVES_AS_BACKLOG, ISSUE_NEXT_BACKLOG_DERIVED, "```text", ISSUE_NEXT_BACKLOG_TO_TRIAGE)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, output)
        offsets = [output.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(output.count("```text"), 1)

    def test_issue_triage_judges_the_state_issue_next_reads_and_cites_that_read_rather_than_restating_it(self):
        _, body = skill_docs()["issue-triage"]
        view = next(line for line in section(body, "Input").splitlines() if "gh issue view" in line)
        self.assertIn(ISSUE_TRIAGE_VIEW, view)
        self.assertIn(ISSUE_TRIAGE_STATE_CITES_ISSUE_NEXT, view)
        self.assertIn(ISSUE_TRIAGE_THIN_BY_STATE, section(body, "State"))
        self.assertIn(ISSUE_TRIAGE_CRITIQUE_STATE, section(body, "Critique"))

    def test_issue_question_takes_one_item_and_every_gh_call_in_the_question_skills_carries_the_repo_as_two_words(self):
        docs = skill_docs()
        self.assertIn(ISSUE_QUESTION_INPUT, section(docs["issue-question"][1], "Input"))
        for name in ("issue-question", "issue-answer"):
            spans = GH_CODE_SPAN.findall(docs[name][1])
            self.assertTrue(spans, name)
            for span in spans:
                with self.subTest(skill=name, call=span):
                    self.assertIn(GH_REPO_FLAG, span)

    def test_issue_question_files_one_comment_then_adds_question_and_takes_ready_off_where_the_tracker_has_it(self):
        _, body = skill_docs()["issue-question"]
        method = re.sub(r"\s+", " ", section(body, "Method"))
        for passage in (QUESTION_COMMENT_HEADING, ISSUE_QUESTION_COMMENT, ISSUE_QUESTION_LABEL_EDIT, ISSUE_QUESTION_LABEL_EDIT_READY):
            with self.subTest(passage=passage):
                self.assertIn(passage, method)
        self.assertLess(method.index(ISSUE_QUESTION_COMMENT), method.index(ISSUE_QUESTION_LABEL_EDIT))

    def test_issue_question_keeps_a_bare_question_label_by_name_and_sets_its_description_or_creates_it_with_that_description(self):
        _, body = skill_docs()["issue-question"]
        method = re.sub(r"\s+", " ", section(body, "Method"))
        step = method[method.index(" 4. "):]
        for passage in (QUESTION_LABEL_DESCRIPTION, ISSUE_QUESTION_LABEL_ADOPT, ISSUE_QUESTION_LABEL_CREATE):
            with self.subTest(passage=passage):
                self.assertIn(passage, step)
        self.assertLess(step.index(QUESTION_LABEL_DESCRIPTION), step.index(ISSUE_QUESTION_LABEL_ADOPT))

    def test_issue_question_retries_the_recommender_once_on_a_disproven_claim_and_runs_none_only_for_the_ready_question(self):
        _, body = skill_docs()["issue-question"]
        method = section(body, "Method")
        self.assertIn("/verify-claim", method)
        self.assertIn("DISPROVEN", method)
        self.assertEqual(method.count(ISSUE_QUESTION_RETRY_ONCE), 1)
        step = next(line for line in method.splitlines() if line.startswith("1. "))
        self.assertTrue(step.startswith(f"1. {ISSUE_QUESTION_READY_QUESTION_NO_RECOMMENDER}"), step)
        self.assertEqual(method.count("no recommender run"), 1)

    def test_issue_question_input_names_the_four_filers_and_the_comment_carries_the_one_that_filed_it(self):
        _, body = skill_docs()["issue-question"]
        inputs = re.sub(r"\s+", " ", section(body, "Input"))
        for filer in ISSUE_QUESTION_FILERS:
            with self.subTest(filer=filer):
                self.assertIn(filer, inputs)
        offsets = [inputs.index(filer) for filer in ISSUE_QUESTION_FILERS]
        self.assertEqual(offsets, sorted(offsets))
        template = re.search(r"```text\n(.*?)```", section(body, "Method"), re.S).group(1)
        self.assertIn(ISSUE_QUESTION_FILED_FROM, template)

    def test_issue_question_briefs_the_recommender_with_the_state_issue_next_reads_and_cites_that_read_rather_than_restating_it(self):
        _, body = skill_docs()["issue-question"]
        step = next(line for line in section(body, "Method").splitlines() if line.startswith("1. "))
        for passage in (ISSUE_QUESTION_VIEW, ISSUE_QUESTION_STATE_CITES_ISSUE_NEXT, ISSUE_QUESTION_RECOMMENDER_STATE):
            with self.subTest(passage=passage):
                self.assertIn(passage, step)
        self.assertLess(step.index(ISSUE_QUESTION_VIEW), step.index(ISSUE_QUESTION_RECOMMENDER_STATE))
        self.assertEqual(body.count("gh issue view"), 1)

    def test_issue_answer_presents_one_item_under_questions_then_posts_the_ruling_and_removes_the_question_label(self):
        _, body = skill_docs()["issue-answer"]
        self.assertIn("`issue-next` § Order", section(body, "Input"))
        self.assertIn("`## Questions`", body)
        self.assertIn(RULING_COMMENT_HEADING, body)
        self.assertIn(ISSUE_ANSWER_LABEL_EDIT, body)
        self.assertLess(body.index("gh issue comment"), body.index(ISSUE_ANSWER_LABEL_EDIT))
        self.assertEqual(body.count(ISSUE_ANSWER_ONE_ITEM), 1)

    def test_every_place_that_states_the_full_question_form_gives_each_option_a_concrete_example_and_code_blocks_only_for_the_real_text_of_a_file_change(self):
        docs = skill_docs()
        method = section(docs["issue-question"][1], "Method")
        places = {
            "claude/CLAUDE.md": questions_paragraph(),
            "recommender": agent_docs()["recommender"][1],
            "issue-question recommender return": method[: method.index("```text")],
            "issue-question comment": re.search(r"```text\n(.*?)```", method, re.S).group(1),
        }
        for place, text in places.items():
            for passage in (QUESTION_EXAMPLE_PER_OPTION, QUESTION_CODE_WHEN, QUESTION_REAL_TEXT_IN_CODE):
                with self.subTest(place=place, passage=passage):
                    self.assertIn(passage, re.sub(r"\s+", " ", text))

    def test_issue_answer_picks_the_first_item_under_question_with_a_question_still_unanswered_in_issue_next_order_and_presents_the_earliest_unanswered_one(self):
        inputs = re.sub(r"\s+", " ", section(skill_docs()["issue-answer"][1], "Input"))
        passages = (ISSUE_ANSWER_LIST, ISSUE_ANSWER_PICK_UNANSWERED, "`issue-next` § Order", ISSUE_ANSWER_RULING_PAIRS, ISSUE_ANSWER_EARLIEST_UNANSWERED)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, inputs)
        offsets = [inputs.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_answer_names_the_items_the_pick_passes_over_in_the_one_line_above_the_question(self):
        _, body = skill_docs()["issue-answer"]
        inputs = re.sub(r"\s+", " ", section(body, "Input"))
        self.assertIn(ISSUE_ANSWER_PASSED_OVER, inputs)
        self.assertLess(inputs.index("is reported in one line"), inputs.index(ISSUE_ANSWER_PASSED_OVER))
        self.assertIn(ISSUE_ANSWER_PASSED_OVER_OUTPUT, re.sub(r"\s+", " ", section(body, "Output")))

    def test_issue_answer_removes_question_only_once_no_question_on_the_item_is_left_unanswered(self):
        rule = section(skill_docs()["issue-answer"][1], "Rule")
        step = next(line for line in rule.splitlines() if ISSUE_ANSWER_LABEL_EDIT in line)
        self.assertIn(ISSUE_ANSWER_NONE_LEFT, step)
        self.assertLess(step.index(ISSUE_ANSWER_NONE_LEFT), step.index(ISSUE_ANSWER_LABEL_EDIT))
        self.assertIn(ISSUE_ANSWER_ANY_LEFT, step)

    def test_issue_answer_presents_in_the_form_claude_md_gives_for_both_forms_and_restates_neither(self):
        present = re.sub(r"\s+", " ", section(skill_docs()["issue-answer"][1], "Present"))
        self.assertIn(ISSUE_ANSWER_PRESENT_FORM, present)
        self.assertIn("under `## Questions`", present)
        for passage in (QUESTION_EXAMPLE_PER_OPTION, QUESTION_CODE_WHEN, QUESTION_REAL_TEXT_IN_CODE, "settles", "obvious", "reference"):
            with self.subTest(passage=passage):
                self.assertNotIn(passage, present)

    def test_issue_answer_rule_routes_the_restart_by_the_filed_from_line_nothing_for_a_ready_ruling_triage_or_the_queue(self):
        _, body = skill_docs()["issue-answer"]
        rule = section(body, "Rule")
        self.assertIn(ISSUE_ANSWER_RESTART, rule)
        self.assertLess(rule.index(ISSUE_ANSWER_LABEL_EDIT), rule.index(ISSUE_ANSWER_RESTART))
        restart = next(line for line in rule.splitlines() if ISSUE_ANSWER_RESTART in line)
        for route in ISSUE_ANSWER_RESTART_ROUTES:
            with self.subTest(route=route):
                self.assertIn(route, restart)
        offsets = [restart.index(route) for route in ISSUE_ANSWER_RESTART_ROUTES]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_answer_ready_ruling_on_the_ready_question_adds_ready_unless_paused_as_it_removes_question(self):
        rule = section(skill_docs()["issue-answer"][1], "Rule")
        step = next(line for line in rule.splitlines() if ISSUE_ANSWER_LABEL_EDIT in line)
        for passage in ISSUE_ANSWER_READY_RULING:
            with self.subTest(passage=passage):
                self.assertIn(passage, step)
        offsets = [step.index(passage) for passage in ISSUE_ANSWER_READY_RULING]
        self.assertEqual(offsets, sorted(offsets))
        self.assertLess(step.index(ISSUE_ANSWER_LABEL_EDIT), offsets[0])
        self.assertLess(offsets[-1], step.index(ISSUE_ANSWER_ANY_LEFT))

    def test_the_ruling_comment_shape_is_fixed_in_issue_answer_and_cited_by_issue_next(self):
        docs = skill_docs()
        output = section(docs["issue-next"][1], "Output")
        self.assertIn(RULING_COMMENT_HEADING, output)
        self.assertIn("`issue-answer`", output)
        self.assertIn(RULING_COMMENT_HEADING, docs["issue-answer"][1])
        self.assertIn(QUESTION_COMMENT_HEADING, docs["issue-answer"][1])

    def test_issue_triage_names_each_of_its_nine_sections_once_and_in_order(self):
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

    def test_issue_triage_question_and_ready_rows_file_through_issue_question_and_add_no_label_themselves(self):
        _, body = skill_docs()["issue-triage"]
        rulings = section(body, "Apply")
        for prefix in ("- question —", "- ready —"):
            with self.subTest(row=prefix):
                line = next(l for l in rulings.splitlines() if l.startswith(prefix))
                self.assertIn("`issue-question`", line)
        self.assertIn(ISSUE_TRIAGE_ROWS_ADD_NO_LABEL, rulings)
        self.assertIn(ISSUE_TRIAGE_FILING_LABEL, rulings)

    def test_issue_triage_ready_row_files_the_ready_question_and_leaves_ready_to_issue_answer(self):
        _, body = skill_docs()["issue-triage"]
        rulings = section(body, "Apply")
        self.assertIn(ISSUE_TRIAGE_READY_EXAMPLE_ROW, rulings)
        row = next(line for line in rulings.splitlines() if line.startswith("- ready —"))
        for passage in ISSUE_TRIAGE_READY_ROW:
            with self.subTest(passage=passage):
                self.assertIn(passage, row)
        self.assertNotIn("--add-label", row)

    def test_issue_triage_every_body_edit_takes_ready_off_an_item_that_carries_it(self):
        _, body = skill_docs()["issue-triage"]
        self.assertIn(ISSUE_TRIAGE_ROWS_TAKE_READY_OFF, re.sub(r"\s+", " ", section(body, "Apply")))

    def test_issue_triage_apply_records_one_row_under_one_ruling_by_precedence_done_duplicate_split_question_ready(self):
        _, body = skill_docs()["issue-triage"]
        rulings = section(body, "Apply")
        self.assertIn(ISSUE_TRIAGE_APPLY_PRECEDENCE, rulings)
        rows = [line[: line.index("—") + 1] for line in rulings.splitlines() if line.startswith("- ")]
        self.assertEqual(rows, list(ISSUE_TRIAGE_APPLY_ROWS))

    def test_issue_triage_split_creates_the_pieces_from_create_step_2_on_and_gives_the_original_one_depends_on_line_per_piece(self):
        _, body = skill_docs()["issue-triage"]
        split = next(line for line in section(body, "Apply").splitlines() if line.startswith("- split —"))
        for passage in ISSUE_TRIAGE_SPLIT_PIECES:
            with self.subTest(passage=passage):
                self.assertIn(passage, split)

    def test_issue_triage_state_runs_draft_duplicate_done_critique_then_ready_and_asks_the_user_nothing(self):
        _, body = skill_docs()["issue-triage"]
        state = re.sub(r"\s+", " ", section(body, "State"))
        for passage in ISSUE_TRIAGE_RUN_ORDER:
            with self.subTest(passage=passage):
                self.assertIn(passage, state)
        offsets = [state.index(passage) for passage in ISSUE_TRIAGE_RUN_ORDER]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn(ISSUE_TRIAGE_NO_ASK, state)

    def test_issue_triage_holds_exactly_the_four_findings_the_user_decides_the_fourth_either_trip_of_the_stop_rule_files_each_with_a_recommender_run_and_ends_the_run(self):
        _, body = skill_docs()["issue-triage"]
        state = re.sub(r"\s+", " ", section(body, "State"))
        for passage in (ISSUE_TRIAGE_HELD_FILED, *ISSUE_TRIAGE_HELD_CLASSES, ISSUE_TRIAGE_HELD_ENDS_RUN):
            with self.subTest(passage=passage):
                self.assertIn(passage, state)
        held = state[state.index(ISSUE_TRIAGE_HELD_FILED) : state.index(ISSUE_TRIAGE_HELD_ENDS_RUN)]
        self.assertEqual(held.count(";"), len(ISSUE_TRIAGE_HELD_CLASSES) - 1, held)
        offsets = [held.index(passage) for passage in ISSUE_TRIAGE_HELD_CLASSES]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_triage_split_ends_the_run_and_the_original_leaves_waiting_on_its_pieces(self):
        _, body = skill_docs()["issue-triage"]
        self.assertIn(ISSUE_TRIAGE_EXITS, re.sub(r"\s+", " ", section(body, "Input")))
        state = re.sub(r"\s+", " ", section(body, "State"))
        self.assertIn(ISSUE_TRIAGE_SPLIT_ENDS_RUN, state)
        self.assertLess(state.index(ISSUE_TRIAGE_HELD_ENDS_RUN), state.index(ISSUE_TRIAGE_SPLIT_ENDS_RUN))

    def test_issue_triage_draft_applies_the_labels_and_the_body_before_anything_else_runs(self):
        _, body = skill_docs()["issue-triage"]
        draft = section(body, "Draft")
        for passage in ISSUE_TRIAGE_DRAFT_APPLIED:
            with self.subTest(passage=passage):
                self.assertIn(passage, draft)
        offsets = [draft.index(passage) for passage in ISSUE_TRIAGE_DRAFT_APPLIED]
        self.assertEqual(offsets, sorted(offsets))

    def test_issue_triage_critique_judges_the_drafted_brief_with_the_items_rulings_in_decisions_made(self):
        _, body = skill_docs()["issue-triage"]
        brief = re.search(r"```text\n(.*?)```", section(body, "Critique"), re.S).group(1)
        for passage in (ISSUE_TRIAGE_CRITIQUE_CHANGE_SET_BRIEF, ISSUE_TRIAGE_CRITIQUE_BRIEF_LINE, ISSUE_TRIAGE_CRITIQUE_DECISIONS):
            with self.subTest(passage=passage):
                self.assertIn(passage, brief)
        self.assertLess(brief.index(ISSUE_TRIAGE_CRITIQUE_CHANGE_SET_BRIEF), brief.index(ISSUE_TRIAGE_CRITIQUE_BRIEF_LINE))

    def test_issue_triage_critique_applies_a_fix_list_as_one_body_edit_and_runs_again_until_the_breaker_holds_a_finding(self):
        _, body = skill_docs()["issue-triage"]
        critique = re.sub(r"\s+", " ", section(body, "Critique"))
        passages = (*ISSUE_TRIAGE_FIX_LIST_APPLIED, ISSUE_TRIAGE_FIX_LIST_HELD_LINE, ISSUE_TRIAGE_BLOCKED_HELD, *ISSUE_TRIAGE_STOP_RULE)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, critique)
        offsets = [critique.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(critique.count("`gh issue edit <N> --body-file <path>`"), 1)

    def test_issue_triage_critique_applies_a_finding_a_ruling_settles_and_counts_a_not_accepted_with_no_line_to_apply_as_accepted(self):
        _, body = skill_docs()["issue-triage"]
        critique = re.sub(r"\s+", " ", section(body, "Critique"))
        for passage in (ISSUE_TRIAGE_RULING_SETTLES, ISSUE_TRIAGE_EMPTY_FIX_LIST):
            with self.subTest(passage=passage):
                self.assertIn(passage, critique)
        self.assertLess(critique.index(ISSUE_TRIAGE_STOP_RULE[-1]), critique.index(ISSUE_TRIAGE_RULING_SETTLES))
        self.assertLess(critique.index("it contributes no line to the fix list."), critique.index(ISSUE_TRIAGE_EMPTY_FIX_LIST))

    def test_issue_triage_ready_posts_brief_plan_and_design_to_the_scratchpad_then_the_item_the_latest_comment_of_each_heading_current(self):
        _, body = skill_docs()["issue-triage"]
        ready = re.sub(r"\s+", " ", section(body, "Ready"))
        for passage in (ISSUE_TRIAGE_EVIDENCE_FILE, ISSUE_TRIAGE_EVIDENCE_POST, ISSUE_TRIAGE_EVIDENCE_LATEST, *ISSUE_TRIAGE_BRIEF_COMMENT, *ISSUE_TRIAGE_PLAN_COMMENT, *ISSUE_TRIAGE_DESIGN_COMMENT):
            with self.subTest(passage=passage):
                self.assertIn(passage, ready)
        bullets = [line for line in section(body, "Ready").splitlines() if line.startswith("- ")]
        self.assertEqual([line[: line.index("—") + 1] for line in bullets], list(ISSUE_TRIAGE_EVIDENCE_BULLETS))
        for bullet, passages in zip(bullets, (ISSUE_TRIAGE_BRIEF_COMMENT, ISSUE_TRIAGE_PLAN_COMMENT, ISSUE_TRIAGE_DESIGN_COMMENT)):
            for passage in passages:
                with self.subTest(bullet=bullet[:14], passage=passage):
                    self.assertIn(passage, bullet)
        self.assertEqual(body.count(ISSUE_TRIAGE_EVIDENCE_FILE), 1)
        self.assertEqual(body.count(ISSUE_TRIAGE_EVIDENCE_POST), 1)

    def test_issue_triage_ready_files_the_ready_question_after_the_evidence_with_no_question_unanswered_and_no_recommender_and_leaves_the_ruling_to_issue_answer(self):
        _, body = skill_docs()["issue-triage"]
        ready = re.sub(r"\s+", " ", section(body, "Ready"))
        passages = (ISSUE_TRIAGE_READY_QUESTION, *ISSUE_TRIAGE_READY_QUESTION_GATE)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, ready)
        offsets = [ready.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))
        self.assertLess(ready.index(ISSUE_TRIAGE_EVIDENCE_BULLETS[-1]), offsets[0])
        self.assertEqual(body.count(ISSUE_TRIAGE_READY_QUESTION), 1)

    def test_issue_triage_closes_a_duplicate_as_a_duplicate_of_the_original_with_the_evidence_in_the_comment_and_adds_no_label(self):
        _, body = skill_docs()["issue-triage"]
        row = next(line for line in section(body, "Apply").splitlines() if line.startswith("- duplicate —"))
        bullet = next(line for line in section(body, "Duplicate").splitlines() if "is a duplicate:" in line)
        for place, text in (("Duplicate", bullet), ("duplicate row", row)):
            with self.subTest(place=place):
                self.assertIn(ISSUE_TRIAGE_DUPLICATE_CLOSE, text)
                self.assertIn(ISSUE_TRIAGE_DUPLICATE_NO_LABEL, text)
                self.assertNotIn("--add-label", text)

    def test_issue_triage_done_closes_only_once_a_remote_branch_contains_every_cited_commit(self):
        _, body = skill_docs()["issue-triage"]
        done = section(body, "Done")
        for passage in ISSUE_TRIAGE_DONE_ORDER:
            with self.subTest(passage=passage):
                self.assertIn(passage, done)
        offsets = [done.index(passage) for passage in ISSUE_TRIAGE_DONE_ORDER]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(body.count(ISSUE_TRIAGE_PUSH_CHECK), 1)
        row = next(line for line in section(body, "Apply").splitlines() if line.startswith("- done —"))
        for passage in ISSUE_TRIAGE_DONE_ROW_CLOSE:
            with self.subTest(passage=passage):
                self.assertIn(passage, row)

    def test_issue_triage_done_keeps_an_item_open_when_no_verdict_cites_a_commit(self):
        _, body = skill_docs()["issue-triage"]
        self.assertIn(ISSUE_TRIAGE_DONE_NO_COMMIT, section(body, "Done"))

    def test_issue_triage_done_has_exactly_one_close_sentence_and_it_follows_the_push_check(self):
        _, body = skill_docs()["issue-triage"]
        done = section(body, "Done")
        sentences = re.split(r"(?<=\.)\s+", done)
        closing = [sentence for sentence in sentences if re.search(r"\bclos", sentence)]
        ruling_done = [sentence for sentence in sentences if re.search(r"\bis done\b", sentence)]
        self.assertEqual(len(closing), 1, closing)
        self.assertEqual(ruling_done, closing)
        self.assertLess(done.index(ISSUE_TRIAGE_PUSH_CHECK), done.index(closing[0]))

    def test_issue_triage_output_names_each_unpushed_commit_or_that_none_was_cited_after_the_lines_no_verdict_verified(self):
        _, body = skill_docs()["issue-triage"]
        output = section(body, "Output")
        self.assertIn(ISSUE_TRIAGE_OUTPUT_UNPUSHED, output)
        self.assertLess(output.index(ISSUE_TRIAGE_OUTPUT_UNVERIFIED), output.index(ISSUE_TRIAGE_OUTPUT_UNPUSHED))

    def test_issue_triage_draft_borrows_refuse_only_to_name_the_missing_sentence_and_holds_it_as_the_question_row_says(self):
        _, body = skill_docs()["issue-triage"]
        draft = section(body, "Draft")
        bullet = next(line for line in draft.splitlines() if ISSUE_TRIAGE_THIN_TEXT_REFUSE in line)
        self.assertIn("missing sentence", bullet)
        self.assertIn(f"held as {ISSUE_TRIAGE_THIN_TEXT_FILED} says", bullet)

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

    def test_deliver_rounds_file_a_deviation_needing_the_user_through_issue_question_pause_the_item_and_verify_a_ruling_premise(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Rounds").splitlines() if "is a deviation:" in line)
        self.assertIn(DELIVER_DEVIATION_FILED, bullet)
        self.assertIn(DELIVER_RULING_PREMISE, bullet)

    def test_deliver_rounds_keep_an_item_with_an_open_ledger_entry_off_the_working_branch_until_the_user_rules(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Rounds").splitlines() if "is a deviation:" in line)
        self.assertIn(DELIVER_OPEN_ENTRY_UNCOMMITTED, bullet)

    def test_deliver_interruptions_session_limit_pauses_each_item_in_flight_before_the_checkpoint(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Interruptions").splitlines() if line.startswith("- On a session-limit error"))
        self.assertIn(DELIVER_SESSION_LIMIT_PAUSES, bullet)

    def test_deliver_interruptions_pause_a_started_item_with_a_tracker_reference_in_ordered_commands_each_on_its_own_then_comment_and_relabel(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Interruptions").splitlines() if line.startswith("- A pause"))
        for passage in (*DELIVER_PAUSE_TRIGGERS, DELIVER_PAUSE_APPLIES_TO, DELIVER_PAUSE_EACH_COMMAND_ALONE, *DELIVER_PAUSE_STEPS):
            with self.subTest(passage=passage):
                self.assertIn(passage, bullet)
        offsets = [bullet.index(passage) for passage in DELIVER_PAUSE_STEPS]
        self.assertEqual(offsets, sorted(offsets))
        self.assertLess(bullet.index(DELIVER_PAUSE_APPLIES_TO), bullet.index(DELIVER_PAUSE_EACH_COMMAND_ALONE))
        self.assertLess(bullet.index(DELIVER_PAUSE_EACH_COMMAND_ALONE), offsets[0])

    def test_deliver_interruptions_resume_a_paused_item_after_the_intake_check_by_fetching_and_cherry_picking_it_uncommitted(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Interruptions").splitlines() if line.startswith("- Before re-dispatching"))
        passages = (DELIVER_RESUME_AFTER_INTAKE, *DELIVER_RESUME_STEPS)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, bullet)
        offsets = [bullet.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))

    def test_deliver_before_commit_deletes_every_paused_branch_of_the_item_locally_and_on_origin_once_it_is_closed(self):
        _, body = skill_docs()["deliver"]
        before = section(body, "Before commit")
        passages = (COMMIT_PUSH_CLOSE, DELIVER_PAUSED_DELETE_AFTER_CLOSE, *DELIVER_PAUSED_DELETE)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, before)
        offsets = [before.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))

    def test_commit_item_footers_the_completing_commit_and_closes_no_issue_itself(self):
        fields, body = skill_docs()["commit-item"]
        self.assertNotIn("close", fields["description"].lower())
        self.assertNotIn("gh issue close", body)
        self.assertIn(COMPLETING_COMMIT_FOOTER, section(body, "Steps"))
        self.assertIn(COMPLETES_THE_ITEM_INPUT, section(body, "Preconditions"))

    def test_commit_item_pushes_its_branch_by_its_literal_name_once_the_commit_is_confirmed_and_reports_the_pushed_branch_before_the_issue_closes(self):
        _, body = skill_docs()["commit-item"]
        steps = section(body, "Steps")
        passages = (COMMIT_ITEM_CONFIRMS_THE_COMMIT, COMMIT_ITEM_PUSH, COMMIT_ITEM_REPORT, COMMIT_ITEM_CLOSES_AFTER_THE_PUSH)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, steps)
        offsets = [steps.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))

    def test_commit_item_description_says_it_pushes_its_branch(self):
        fields, _ = skill_docs()["commit-item"]
        self.assertIn(COMMIT_ITEM_DESCRIPTION_PUSH, fields["description"])

    def test_deliver_before_commit_orders_commit_push_close_by_the_git_rule(self):
        _, body = skill_docs()["deliver"]
        self.assertIn(COMMIT_PUSH_CLOSE, section(body, "Before commit"))

    def test_deliver_intake_tiers_every_item_and_runs_only_a_trivial_one_liner_inline(self):
        _, body = skill_docs()["deliver"]
        intake = section(body, "Intake and tiering")
        self.assertIn(DELIVER_TIERS_EVERY_ITEM, intake)
        self.assertIn(DELIVER_TRIVIAL_INLINE, intake)

    def test_deliver_intake_takes_a_tracker_items_brief_from_issue_next_resolves_its_paths_at_the_root_and_hands_plan_phases_the_plan_comment(self):
        _, body = skill_docs()["deliver"]
        intake = re.sub(r"\s+", " ", section(body, "Intake and tiering"))
        passages = (DELIVER_TRIVIAL_INLINE, DELIVER_INTAKE_BRIEF_FROM_ISSUE_NEXT, DELIVER_INTAKE_PATHS_RESOLVE_AT_THE_ROOT, DELIVER_INTAKE_PLAN_COMMENT)
        for passage in passages:
            with self.subTest(passage=passage):
                self.assertIn(passage, intake)
        offsets = [intake.index(passage) for passage in passages]
        self.assertEqual(offsets, sorted(offsets))

    def test_deliver_intake_files_a_brief_the_tree_contradicts_through_issue_question_from_intake_and_runs_nothing(self):
        _, body = skill_docs()["deliver"]
        bullet = next(line for line in section(body, "Intake and tiering").splitlines() if DELIVER_INTAKE_CHECKS_THE_BRIEF in line)
        for passage in DELIVER_INTAKE_CONTRADICTION:
            with self.subTest(passage=passage):
                self.assertIn(passage, bullet)
        offsets = [bullet.index(passage) for passage in DELIVER_INTAKE_CONTRADICTION]
        self.assertEqual(offsets, sorted(offsets))
        self.assertLess(bullet.index(DELIVER_INTAKE_CHECKS_THE_BRIEF), offsets[0])

    def test_deliver_intake_checks_the_brief_before_the_item_runs_inline_or_dispatched_so_a_trivial_item_is_checked_too(self):
        _, body = skill_docs()["deliver"]
        lines = section(body, "Intake and tiering").splitlines()
        trivial = next(line for line in lines if DELIVER_TRIVIAL_INLINE in line)
        check = next(line for line in lines if DELIVER_INTAKE_CONTRADICTION[0] in line)
        trigger = check[: check.index(DELIVER_INTAKE_CONTRADICTION[0])]
        self.assertTrue(trigger.startswith(f"- {DELIVER_INTAKE_CHECKS_THE_BRIEF} "), trigger)
        inline = re.search(r"runs `implement` (\w+)", trivial).group(1)
        for path in (inline, "dispatched"):
            with self.subTest(path=path):
                self.assertIn(path, trigger)

    def test_deliver_intake_files_from_a_value_issue_question_accepts_and_issue_answer_routes_to_triage(self):
        docs = skill_docs()
        self.assertIn(f"`Filed from: {DELIVER_INTAKE_FILED_FROM}`", section(docs["deliver"][1], "Intake and tiering"))
        template = re.search(r"```text\n(.*?)```", section(docs["issue-question"][1], "Method"), re.S).group(1)
        allowed = re.search(r"Filed from: <(.*?)>", template).group(1).split(" | ")
        self.assertIn(DELIVER_INTAKE_FILED_FROM, allowed)
        restart = next(line for line in section(docs["issue-answer"][1], "Rule").splitlines() if ISSUE_ANSWER_RESTART in line)
        clause = next(clause for clause in restart.split("; ") if f"`{DELIVER_INTAKE_FILED_FROM}`" in clause)
        self.assertTrue(clause.startswith("`issue-triage` on the item"), clause)

    def test_issue_writer_files_its_questions_from_a_value_issue_question_accepts_and_issue_answer_routes_to_triage(self):
        docs = skill_docs()
        self.assertIn(f"`Filed from: {ISSUE_WRITE_FILED_FROM}`", agent_docs()["issue-writer"][1])
        template = re.search(r"```text\n(.*?)```", section(docs["issue-question"][1], "Method"), re.S).group(1)
        allowed = re.search(r"Filed from: <(.*?)>", template).group(1).split(" | ")
        self.assertIn(ISSUE_WRITE_FILED_FROM, allowed)
        restart = next(line for line in section(docs["issue-answer"][1], "Rule").splitlines() if ISSUE_ANSWER_RESTART in line)
        clause = next(clause for clause in restart.split("; ") if f"`{ISSUE_WRITE_FILED_FROM}`" in clause)
        self.assertTrue(clause.startswith("`issue-triage` on the item"), clause)

    def test_design_surface_exit_returns_the_locked_design_hands_it_to_deliver_or_back_to_triage_and_instructs_no_write(self):
        _, body = skill_docs()["design-surface"]
        self.assertIn(DESIGN_EXIT_RETURNS_THE_DESIGN, section(body, "Exit"))
        self.assertNotIn("writ", body.lower())

    def test_design_surface_sends_load_bearing_claims_to_verify_claim_before_a_proposal_reaches_the_user_or_returns_to_triage(self):
        _, body = skill_docs()["design-surface"]
        self.assertIn(DESIGN_CLAIMS_VERIFIED_BEFORE_THE_USER_OR_TRIAGE, section(body, "Method"))

    def test_design_surface_output_puts_a_user_decision_to_the_user_or_returns_it_as_a_finding_for_triage_to_hold_asking_the_user_nothing_and_leaves_the_surface_unlocked_until_the_ruling_restarts_triage(self):
        _, body = skill_docs()["design-surface"]
        bullet = next(line for line in section(body, "Output").splitlines() if line.startswith("- **Risks and open questions**"))
        self.assertIn(DESIGN_USER_DECISION_PUT_OR_RETURNED, bullet)

    def test_design_surface_every_sentence_naming_the_user_also_says_what_happens_when_triage_ran_it(self):
        fields, body = skill_docs()["design-surface"]
        sentences = [sentence for sentence in re.split(r"(?<=[.!?])\s+", f"{fields['description']} {body}") if "user" in sentence]
        self.assertTrue(sentences)
        for sentence in sentences:
            with self.subTest(sentence=sentence[:60]):
                self.assertIn("triage", sentence)

    def test_deliver_rounds_send_bulk_and_interpreting_reads_to_the_tier_researcher_and_brief_the_memo(self):
        _, body = skill_docs()["deliver"]
        rounds = section(body, "Rounds")
        for passage in (DELIVER_RESEARCH_READS, DELIVER_MEMO_ENTERS_THE_BRIEF):
            with self.subTest(passage=passage):
                self.assertIn(passage, rounds)

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

    def test_research_routing_sends_an_enumerating_lane_to_trivial_and_an_interpreting_lane_by_its_item_tier(self):
        tiers = read(SKILLS / "deliver" / "references" / "tiers.md")
        for row in RESEARCH_ROUTING_ROWS:
            with self.subTest(row=row):
                self.assertEqual(tiers.count(row), 1)

    def test_blast_radius_keeps_an_item_out_of_trivial_and_never_makes_it_complex(self):
        lines = read(SKILLS / "deliver" / "references" / "tiers.md").splitlines()
        trivial = next(line for line in lines if line.startswith("- `trivial` —"))
        complex_ = next(line for line in lines if line.startswith("- `complex` —"))
        self.assertIn("blast radius", trivial)
        self.assertNotIn("blast radius", complex_)

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


def deliver_commands(text):
    message = f"{DELIVER_PAUSED_SUBJECT}\n\nWorking branch: <working branch>. Done: the helper. Next step: its test.\n\n{DELIVER_PAUSED_FOOTER}"
    commands = []
    for span in re.findall(r"`([^`]+)`", text):
        if not span.startswith(("git ", "gh ")):
            continue
        command = span.replace(" … ", f"\n{message}\n")
        for placeholder, value in PAUSE_PLACEHOLDERS:
            command = command.replace(placeholder, value)
        commands.append(command)
    return commands


class DeliverPauseGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.root = os.path.realpath(directory.name)
        environment = {"HOME": cls.root, "XDG_CONFIG_HOME": os.path.join(cls.root, ".config"), "GIT_CONFIG_SYSTEM": os.devnull}
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.paused = os.path.join(cls.root, "paused")
        subprocess.run(["git", "init", "-q", "-b", "paused/12-1", cls.paused], check=True, capture_output=True)

    def judged(self, command):
        return git_guard.evaluate({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": self.paused, "tool_input": {"command": command}})

    def test_the_guard_permits_every_pause_resume_and_delete_command_deliver_runs_each_on_its_own_on_a_paused_branch(self):
        _, body = skill_docs()["deliver"]
        commands = deliver_commands(section(body, "Interruptions") + section(body, "Before commit"))
        self.assertIn("git push origin paused/12-1", commands)
        self.assertIn("git push origin --delete paused/12-1", commands)
        self.assertTrue(any(command.startswith("git commit -F - -- a <<'EOF'\nchore(paused): paused work for #12\n") for command in commands), commands)
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self.judged(command))

    def test_the_paused_commit_subject_is_conventional(self):
        self.assertRegex(DELIVER_PAUSED_SUBJECT.replace("<N>", "12"), git_guard.CONVENTIONAL_SUBJECT)


class CommitItemPushGuardTest(unittest.TestCase):
    def test_the_guard_permits_the_one_push_commit_item_runs_on_a_working_branch_and_on_main(self):
        _, body = skill_docs()["commit-item"]
        pushes = [span for span in re.findall(r"`([^`]+)`", section(body, "Steps")) if span.startswith("git push")]
        self.assertEqual(len(pushes), 1, pushes)
        with tempfile.TemporaryDirectory() as cwd:
            for branch in ("feature/93-push", "main"):
                command = pushes[0].replace("<branch>", branch)
                with self.subTest(command=command):
                    self.assertIsNone(git_guard.evaluate({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}}))


def phrase_homes(phrase, tree=CLAUDE):
    return {str(p.relative_to(REPO)) for p in payload_files() if p.is_relative_to(tree) and phrase in read(p)}


def text_files(tree):
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        try:
            yield path, read(path)
        except UnicodeDecodeError:
            continue


def assert_description(case, description):
    case.assertTrue(description)
    case.assertLessEqual(len(description), DESCRIPTION_MAX)
    for prefix in ("I ", "You ", "Use this"):
        case.assertFalse(description.startswith(prefix), description)


if __name__ == "__main__":
    unittest.main()
