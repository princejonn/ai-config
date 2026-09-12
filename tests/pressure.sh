#!/bin/bash
# Pressure-tests skill triggering: per skill one prompt that must fire it and one that must not, run
# through `claude -p` in a fresh scratch project. Spends tokens; on demand.
# A `/name` prompt the CLI expands emits no Skill event, so its proxy is the session transcript entry.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd -P)"
SKILLS_DIR="$HERE/../claude/skills"
TIMEOUT=120
GRACE=5
MAX_TURNS=2

SKILL=()
FIRE=()
NOFIRE=()
pair() {
  SKILL+=("$1")
  FIRE+=("$2")
  NOFIRE+=("$3")
}

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
  'Add a strict keyword to render in widget.py that raises ValueError on an empty name.' \
  'Which is the better public surface here, a strict flag on render or a separate render_strict function?'
pair issue-next \
  'What should I work on next?' \
  'Turn this finding into an issue: render accepts an empty name and returns an empty tag.'
pair issue-triage \
  'Triage issue #15 — it reads complete but I want it challenged before we start.' \
  'Which open issue is the most urgent?'
pair issue-write \
  'Turn this finding into an issue: render accepts an empty name and returns an empty tag.' \
  'Triage issue #15 before we start on it — challenge its proposal.'
pair plan-phases \
  'Give me a phased execution plan for splitting widget.py into a package, with invariants and an exit check per phase.' \
  'Rename widget.py to renderer.py and update the README.'
pair research \
  'Find every call site of render in this repository and list them.' \
  'Read widget.py and tell me what render returns when name is empty.'
pair research-complex \
  'Work out what RFC 3986 section 2.3 requires of unreserved characters; the design rests on the answer.' \
  'List every Python file in this repository.'
pair review-change \
  'Review the staged change-set against its brief and give me ACCEPTED or NOT ACCEPTED.' \
  'Get Codex to look at this diff.'
pair second-opinion-codex \
  'Get Codex to attack the premises of this plan before we accept it.' \
  'Review this change-set against its brief and tell me whether it is acceptable.'
pair test \
  'test_render_empty fails one run in twenty on CI — diagnose the flake within 200 runs.' \
  'render returns the wrong string for an empty name and the cause is not known — find it.'
pair verify-claim \
  'Before I rely on it: is it true that nothing else calls render? Check that claim.' \
  'Find every function defined in this repository.'

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

index_of() {
  local wanted="$1" i=0
  while [ "$i" -lt "${#SKILL[@]}" ]; do
    if [ "${SKILL[$i]}" = "$wanted" ]; then echo "$i"; return 0; fi
    i=$((i + 1))
  done
  return 1
}

missing=""
for directory in "$SKILLS_DIR"/*/; do
  name="$(basename "$directory")"
  index_of "$name" >/dev/null || missing="$missing $name"
done
if [ -n "$missing" ]; then
  echo "pressure: no prompt pair for:$missing" >&2
  exit 2
fi

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
  index_of "$only" >/dev/null || { echo "pressure: no prompt pair named $only" >&2; exit 2; }
  selected=("$(index_of "$only")")
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
  echo "claude -p $(single_quoted "$1") --output-format stream-json --verbose --max-turns $MAX_TURNS </dev/null"
}

if $dry_run; then
  for i in "${selected[@]}"; do
    echo "${SKILL[$i]}"
    echo "  fire    $(command_line "${FIRE[$i]}")"
    echo "  no-fire $(command_line "${NOFIRE[$i]}")"
  done
  exit 0
fi

run_prompt() {
  local stream="$1" prompt="$2" pid waited
  # exec, so $! is claude itself: killing the subshell around it would leave claude orphaned.
  (cd "$PROJECT" && exec claude -p "$prompt" --output-format stream-json --verbose --max-turns "$MAX_TURNS") \
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
  python3 - "$1" "$2" "${3-}" <<'PY'
import json
import sys

stream, question, skill = sys.argv[1], sys.argv[2], sys.argv[3]

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
        if block.get("name") != "Skill":
            continue
        argument = block.get("input")
        if not isinstance(argument, dict):
            continue
        name = argument.get("skill")
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
  transcript="$(find "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects" -maxdepth 2 -name "$session.jsonl" 2>/dev/null | head -1)"
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
git -C "$PROJECT" init -q
git -C "$PROJECT" add -A
echo "scratch $ROOT"

passed=0
failed=0
for i in "${selected[@]}"; do
  skill="${SKILL[$i]}"
  run_prompt "$STREAMS/$skill.fire.jsonl" "${FIRE[$i]}"
  fire_result="$(stream_query "$STREAMS/$skill.fire.jsonl" result-subtype)"
  if fired "$STREAMS/$skill.fire.jsonl" "$skill" "${FIRE[$i]}"; then fire=yes; else fire=no; fi
  run_prompt "$STREAMS/$skill.nofire.jsonl" "${NOFIRE[$i]}"
  nofire_result="$(stream_query "$STREAMS/$skill.nofire.jsonl" result-subtype)"
  nofire="$(nofire_verdict "$STREAMS/$skill.nofire.jsonl" "$skill" "${NOFIRE[$i]}")"
  unfinished=""
  [ -n "$fire_result" ] || unfinished="$unfinished $STREAMS/$skill.fire.jsonl.err"
  [ -n "$nofire_result" ] || unfinished="$unfinished $STREAMS/$skill.nofire.jsonl.err"
  if [ "$fire" = yes ] && [ "$nofire" = no ]; then
    echo "PASS $skill"
    passed=$((passed + 1))
  else
    echo "FAIL $skill fire=$fire nofire=$nofire$unfinished"
    failed=$((failed + 1))
  fi
done

echo "PASS $passed FAIL $failed"
[ "$failed" = 0 ]
