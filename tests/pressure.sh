#!/bin/bash
# Pressure-tests skill triggering: per pair one prompt that must fire its skill and one that must not,
# run through `claude -p` in a fresh scratch project. Spends tokens; on demand.
# A `/name` prompt the CLI expands emits no Skill event, so its proxy is the session transcript entry.
# A skill preloaded in an agent emits none either: a dispatch to an agent whose `skills:` in this tree
# is that one skill counts as it firing, and so does a dispatch to an agent preloading several when
# claude/CLAUDE.md routes the skill under test to that agent and the dispatch prompt names that skill
# as a word before any other skill the agent preloads.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd -P)"
CONFIG_DIR="$HERE/../claude"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILLS_DIR="$CONFIG_DIR/skills"
AGENTS_DIR="$CONFIG_DIR/agents"
ROUTING="$CONFIG_DIR/CLAUDE.md"
TIMEOUT=120
GRACE=5
MAX_TURNS=3

SKILL=()
FIRE=()
NOFIRE=()
pair() {
  SKILL+=("$1")
  FIRE+=("$2")
  NOFIRE+=("$3")
}

pair author-gherkin \
  'Write the feature file for the public surface of widget.py.' \
  'test_render_empty fails one run in twenty on CI — diagnose the flake within 200 runs.'
pair author-skill \
  'Add a new skill to my ai-config repo for summarising a changelog and word its description so it fires on the right prompts.' \
  'Rename the render function in widget.py to draw.'
pair commit-item \
  '/commit-item' \
  'show me the git status'
pair deliver \
  'We agreed on adding a slugify helper to widget.py — take it all the way to committable code.' \
  'Weigh a separator argument against a full options object for a new slugify helper — which public surface should we settle on?'
pair design-surface \
  'Compare the option shapes and error contracts for a strict mode on render before we change the surface.' \
  'Implement the strict mode on render exactly as agreed: an empty name raises ValueError.'
pair diagnose-root-cause \
  'render returns the wrong string for an empty name and the cause is not known — find it.' \
  'Prove the pinning test for render goes red before the fix.'
pair implement \
  'Refactor render in widget.py to build its string with an f-string; its output stays the same.' \
  'Which is the better public surface here, a strict flag on render or a separate render_strict function?'
pair issue-answer \
  'Which questions are open on the tracker and waiting on me? Give me the first one to rule on.' \
  'Add a docstring to render in widget.py.'
pair issue-next \
  'What should I work on next?' \
  'Turn this finding into an issue: render accepts an empty name and returns an empty tag.'
pair issue-question \
  'File this question on issue #15 with a recommendation: should render raise on an empty name or return an empty tag? Take the item out of the queue until I answer.' \
  'Add a type hint to the name argument of render in widget.py.'
pair issue-triage \
  'Triage issue #15 — it reads complete but I want it challenged before we start.' \
  'Which open issue is the most urgent?'
pair issue-write \
  'Turn this finding into an issue: render accepts an empty name and returns an empty tag.' \
  'Triage issue #15 before we start on it — challenge its proposal.'
pair open-pull-request \
  'Open a pull request from the branch I just pushed and show me the preview before you create it.' \
  'Commit the accepted change-set for #15 by its paths and push its branch.'
pair plan-phases \
  'Give me a phased execution plan for splitting widget.py into a package, with invariants and an exit check per phase.' \
  'Rename widget.py to renderer.py and update the README.'
pair research \
  'Find every call site of render in this repository and list them.' \
  'Before I rely on it: is it true that nothing else calls render? Check that claim.'
pair research \
  'Work out what RFC 3986 section 2.3 requires of unreserved characters; the design rests on the answer.' \
  'Review the staged change-set against its brief and give me ACCEPTED or NOT ACCEPTED.'
pair review-change \
  'Review the staged change-set against this brief and give me ACCEPTED or NOT ACCEPTED. Goal: render wraps a name in angle brackets. Acceptance: render("x") → "<x>". Files in scope: widget.py, test_widget.py. Tier: trivial.' \
  'Get Codex to look at this diff.'
pair second-opinion-codex \
  'Get Codex to attack the premises of this plan before we accept it.' \
  'Review this change-set against its brief and tell me whether it is acceptable.'
pair test \
  'test_render_empty fails one run in twenty on CI — diagnose the flake within 200 runs.' \
  'render returns the wrong string for an empty name and the cause is not known — find it.'
pair test \
  'Prove test_render_empty actually bites — mutate render in widget.py red and show me the test go red.' \
  'Add a mutate helper to widget.py that returns a copy of a dict with one key changed.'
pair verify-claim \
  'Before I rely on it: is it true that nothing else calls render? Check that claim.' \
  'List the arguments render takes in widget.py.'

usage() {
  echo "usage: $(basename "$0") [--only <skill>] [--dry-run] [--verdict <stream> <skill> <prompt>]" >&2
  exit 2
}

only=""
dry_run=false
verdict=false
verdict_stream=""
verdict_skill=""
verdict_prompt=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only)
      [ $# -ge 2 ] || usage
      only="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --verdict)
      [ $# -ge 4 ] || usage
      verdict=true
      verdict_stream="$2"
      verdict_skill="$3"
      verdict_prompt="$4"
      shift 4
      ;;
    *) usage ;;
  esac
done

# A skill may carry more than one pair, one per trigger surface; --only runs every pair it has.
indices_of() {
  local wanted="$1" i=0 found=1
  while [ "$i" -lt "${#SKILL[@]}" ]; do
    if [ "${SKILL[$i]}" = "$wanted" ]; then echo "$i"; found=0; fi
    i=$((i + 1))
  done
  return "$found"
}

tag_of() {
  local wanted="$1" index="$2" ordinal=0 i=0
  while [ "$i" -lt "$index" ]; do
    [ "${SKILL[$i]}" = "$wanted" ] && ordinal=$((ordinal + 1))
    i=$((i + 1))
  done
  if [ "$ordinal" = 0 ]; then echo "$wanted"; else echo "$wanted-$((ordinal + 1))"; fi
}

unknown=""
for name in "${SKILL[@]}"; do
  [ -d "$SKILLS_DIR/$name" ] || unknown="$unknown $name"
done
if [ -n "$unknown" ]; then
  echo "pressure: pair names no skill directory:$unknown" >&2
  exit 2
fi

selected=()
if [ -n "$only" ]; then
  indices_of "$only" >/dev/null || { echo "pressure: no prompt pair named $only" >&2; exit 2; }
  while IFS= read -r index; do selected+=("$index"); done < <(indices_of "$only")
else
  i=0
  while [ "$i" -lt "${#SKILL[@]}" ]; do
    selected+=("$i")
    i=$((i + 1))
  done
fi

single_quoted() {
  local escaped=${1//\'/\'\\\'\'}
  echo "'$escaped'"
}

command_line() {
  echo "claude -p $(single_quoted "$1") --output-format stream-json --verbose --max-turns $MAX_TURNS --add-dir $(single_quoted "$CONFIG_DIR") $(single_quoted "$CLAUDE_HOME") </dev/null"
}

if $dry_run; then
  for i in "${selected[@]}"; do
    tag_of "${SKILL[$i]}" "$i"
    echo "  fire    $(command_line "${FIRE[$i]}")"
    echo "  no-fire $(command_line "${NOFIRE[$i]}")"
  done
  exit 0
fi

run_prompt() {
  local stream="$1" prompt="$2" pid waited
  # exec, so $! is claude itself: killing the subshell around it would leave claude orphaned.
  # --add-dir, because the session starts in default permission mode, where a read outside the
  # project is denied with no one to prompt and a skill's references stay unread.
  (cd "$PROJECT" && exec claude -p "$prompt" --output-format stream-json --verbose --max-turns "$MAX_TURNS" --add-dir "$CONFIG_DIR" "$CLAUDE_HOME") \
    >"$stream" 2>"$stream.err" </dev/null &
  pid=$!
  waited=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge "$TIMEOUT" ]; then
      kill -TERM "$pid" 2>/dev/null || true
      waited=0
      while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$GRACE" ]; do
        sleep 1
        waited=$((waited + 1))
      done
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$pid" >/dev/null 2>&1 || true
}

stream_query() {
  python3 - "$AGENTS_DIR" "$ROUTING" "$1" "$2" "${3-}" <<'PY'
import json
import re
import sys
from pathlib import Path

agents, routing, stream, question, skill = sys.argv[1:6]


def preloaded(path):
    frontmatter = path.read_text(encoding="utf-8").split("\n---\n", 1)[0]
    line = re.search(r"^skills:(.*)$", frontmatter, re.MULTILINE)
    return re.findall(r"[a-z0-9-]+", line.group(1)) if line else []


preloads = {path.stem: preloaded(path) for path in Path(agents).glob("*.md")}
routing_table = Path(routing).read_text(encoding="utf-8")
row = re.search(r"^\| `%s` \|(.*)$" % re.escape(skill), routing_table, re.MULTILINE)
routed_to = set(re.findall(r"`([^`]+)`", row.group(1))) if row else set()


def dispatched_skill(agent, prompt):
    skills = preloads.get(agent, [])
    if len(skills) == 1:
        return skills[0]
    named = [word for word in re.findall(r"[\w-]+", prompt) if word in skills]
    return skill if agent in routed_to and named[:1] == [skill] else None


session = None
subtype = ""
chosen = []
for line in open(stream, encoding="utf-8", errors="replace"):
    line = line.strip()
    if not line:
        continue
    try:
        event = json.loads(line)
    except ValueError:
        continue
    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        if session is None:
            session = event.get("session_id", "")
        continue
    if kind == "result":
        subtype = event.get("subtype", "")
        continue
    if kind != "assistant":
        continue
    content = event.get("message", {}).get("content")
    if not isinstance(content, list):
        continue
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        argument = block.get("input")
        if not isinstance(argument, dict):
            continue
        if block.get("name") == "Skill":
            name = argument.get("skill")
        elif block.get("name") == "Agent" and isinstance(argument.get("subagent_type"), str):
            prompt = argument.get("prompt")
            name = dispatched_skill(argument["subagent_type"], prompt if isinstance(prompt, str) else "")
        else:
            continue
        if isinstance(name, str):
            chosen.append(name)

if question == "session-id":
    print(session or "")
elif question == "result-subtype":
    print(subtype)
elif question == "skill-used":
    print("yes" if skill in chosen else "no")
elif question == "other-skill-used":
    print("yes" if [name for name in chosen if name != skill] else "no")
else:
    sys.exit("stream_query: unknown question %s" % question)
PY
}

command_expanded() {
  local session transcript
  session="$(stream_query "$1" session-id)"
  [ -n "$session" ] || return 1
  transcript="$(find "$CLAUDE_HOME/projects" -maxdepth 2 -name "$session.jsonl" 2>/dev/null | head -1)"
  [ -n "$transcript" ] || return 1
  grep -qE "<command-name>/?$2</command-name>" "$transcript"
}

fired() {
  local stream="$1" skill="$2" prompt="$3"
  case "$prompt" in
    /*) command_expanded "$stream" "$skill" ;;
    *) [ "$(stream_query "$stream" skill-used "$skill")" = yes ] ;;
  esac
}

nofire_verdict() {
  local stream="$1" skill="$2" prompt="$3"
  if fired "$stream" "$skill" "$prompt"; then
    echo yes
  elif [ "$(stream_query "$stream" other-skill-used "$skill")" = yes ]; then
    echo no
  elif [ "$(stream_query "$stream" result-subtype)" = success ]; then
    echo no
  else
    echo cut
  fi
}

if $verdict; then
  [ -f "$verdict_stream" ] || { echo "pressure: no stream at $verdict_stream" >&2; exit 2; }
  nofire_verdict "$verdict_stream" "$verdict_skill" "$verdict_prompt"
  exit 0
fi

command -v claude >/dev/null 2>&1 || { echo "pressure: claude is not on PATH" >&2; exit 2; }

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ai-config-pressure.XXXXXX")"
ROOT="$(cd "$ROOT" && pwd -P)"
# The streams stay outside the project: a log inside it is a file the prompt under test reads.
PROJECT="$ROOT/project"
STREAMS="$ROOT/streams"
mkdir "$PROJECT" "$STREAMS"
printf '%s\n' '# widget' '' 'A small widget library.' > "$PROJECT/README.md"
printf '%s\n' 'def render(name):' '    return "<" + name + ">"' > "$PROJECT/widget.py"
# A prompt naming test_render_empty is answered by challenging the premise where no such test exists.
printf '%s\n' 'from widget import render' '' '' 'def test_render_empty():' '    assert render("") == "<>"' > "$PROJECT/test_widget.py"
git -C "$PROJECT" init -q
git -C "$PROJECT" add -A
echo "scratch $ROOT"

passed=0
failed=0
for i in "${selected[@]}"; do
  skill="${SKILL[$i]}"
  tag="$(tag_of "$skill" "$i")"
  run_prompt "$STREAMS/$tag.fire.jsonl" "${FIRE[$i]}"
  fire_result="$(stream_query "$STREAMS/$tag.fire.jsonl" result-subtype)"
  if fired "$STREAMS/$tag.fire.jsonl" "$skill" "${FIRE[$i]}"; then fire=yes; else fire=no; fi
  run_prompt "$STREAMS/$tag.nofire.jsonl" "${NOFIRE[$i]}"
  nofire_result="$(stream_query "$STREAMS/$tag.nofire.jsonl" result-subtype)"
  nofire="$(nofire_verdict "$STREAMS/$tag.nofire.jsonl" "$skill" "${NOFIRE[$i]}")"
  unfinished=""
  [ -n "$fire_result" ] || unfinished="$unfinished $STREAMS/$tag.fire.jsonl.err"
  [ -n "$nofire_result" ] || unfinished="$unfinished $STREAMS/$tag.nofire.jsonl.err"
  if [ "$fire" = yes ] && [ "$nofire" = no ]; then
    echo "PASS $tag"
    passed=$((passed + 1))
  else
    echo "FAIL $tag fire=$fire nofire=$nofire$unfinished"
    failed=$((failed + 1))
  fi
done

echo "PASS $passed FAIL $failed"
[ "$failed" = 0 ]
