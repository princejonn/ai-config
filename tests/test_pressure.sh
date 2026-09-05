#!/bin/bash
set -u

HERE="$(cd "$(dirname "$0")" && pwd -P)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ai-config-pressure-test.XXXXXX")" || exit 1
WORK="$(cd "$WORK" && pwd -P)" || exit 1
trap 'rm -rf "$WORK"' EXIT

ERR="$WORK/err"
PROMPT='Tidy up the labels on the open issues.'

pass=0
fail=0
check() {
  if [ "$1" = 0 ]; then
    echo "PASS $2"
    pass=$((pass + 1))
  else
    echo "FAIL $2"
    cat "$ERR" >&2
    fail=$((fail + 1))
  fi
}

init_event() {
  printf '{"type":"system","subtype":"init","session_id":"pressure-fixture"}\n'
}

text_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"text","text":"%s"}]}}\n' "$1"
}

skill_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"%s"}}]}}\n' "$1"
}

bare_skill_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{}}]}}\n'
}

result_event() {
  printf '{"type":"result","subtype":"%s"}\n' "$1"
}

verdict=""
status=0
run_verdict() {
  verdict="$(/bin/bash "$HERE/pressure.sh" --verdict "$1" "$2" "$3" 2>"$ERR")"
  status=$?
}

SIBLING="$WORK/sibling.jsonl"
{ init_event; skill_event issue-write; result_event error_max_turns; } > "$SIBLING"
run_verdict "$SIBLING" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = no ]
check $? "1 a Skill call naming a sibling in a stream cut at the turn cap is no"

SUCCEEDED="$WORK/succeeded.jsonl"
{ init_event; text_event "the labels are tidy"; result_event success; } > "$SUCCEEDED"
run_verdict "$SUCCEEDED" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = no ]
check $? "2 no Skill call in a stream that ended success is no"

CUT="$WORK/cut.jsonl"
{ init_event; text_event "reading the backlog"; result_event error_max_turns; } > "$CUT"
run_verdict "$CUT" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = cut ]
check $? "3 no Skill call in a stream cut at the turn cap is cut"

FIRED="$WORK/fired.jsonl"
{ init_event; skill_event issue-next; result_event success; } > "$FIRED"
run_verdict "$FIRED" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = yes ]
check $? "4 a Skill call naming the skill under test is yes"

FIRED_CUT="$WORK/fired-cut.jsonl"
{ init_event; skill_event issue-next; result_event error_max_turns; } > "$FIRED_CUT"
run_verdict "$FIRED_CUT" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = yes ]
check $? "5 a Skill call naming the skill under test in a stream cut at the turn cap is yes"

SIBLING_THEN_FIRED="$WORK/sibling-then-fired.jsonl"
{ init_event; skill_event issue-write; skill_event issue-next; result_event error_max_turns; } \
  > "$SIBLING_THEN_FIRED"
run_verdict "$SIBLING_THEN_FIRED" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = yes ]
check $? "6 the skill under test after a sibling in the same stream is yes"

NAMELESS="$WORK/nameless.jsonl"
{ init_event; bare_skill_event; result_event error_max_turns; } > "$NAMELESS"
run_verdict "$NAMELESS" issue-next "$PROMPT"
[ "$status" = 0 ] && [ ! -s "$ERR" ] && [ "$verdict" = cut ]
check $? "7 a Skill call carrying no skill name in a stream cut at the turn cap is cut"

echo "PASS $pass FAIL $fail"
[ "$fail" = 0 ]
