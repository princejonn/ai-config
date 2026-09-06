#!/bin/bash
set -u

SCRATCH=ai-config-pressure-test
. "$(dirname "$0")/lib.sh"

ERR="$WORK/err"
FAIL_DUMP="$ERR"
PROMPT='Tidy up the labels on the open issues.'

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

verdict_is() {
  [ "$status" = 0 ]; check $? "$2 exits 0"
  [ ! -s "$ERR" ]; check $? "$2 prints nothing on stderr"
  [ "$verdict" = "$1" ]; check $? "$2 is $1"
}

SIBLING="$WORK/sibling.jsonl"
{ init_event; skill_event issue-write; result_event error_max_turns; } > "$SIBLING"
run_verdict "$SIBLING" issue-next "$PROMPT"
verdict_is no "1 a Skill call naming a sibling in a stream cut at the turn cap"

SUCCEEDED="$WORK/succeeded.jsonl"
{ init_event; text_event "the labels are tidy"; result_event success; } > "$SUCCEEDED"
run_verdict "$SUCCEEDED" issue-next "$PROMPT"
verdict_is no "2 no Skill call in a stream that ended success"

CUT="$WORK/cut.jsonl"
{ init_event; text_event "reading the backlog"; result_event error_max_turns; } > "$CUT"
run_verdict "$CUT" issue-next "$PROMPT"
verdict_is cut "3 no Skill call in a stream cut at the turn cap"

FIRED="$WORK/fired.jsonl"
{ init_event; skill_event issue-next; result_event success; } > "$FIRED"
run_verdict "$FIRED" issue-next "$PROMPT"
verdict_is yes "4 a Skill call naming the skill under test"

FIRED_CUT="$WORK/fired-cut.jsonl"
{ init_event; skill_event issue-next; result_event error_max_turns; } > "$FIRED_CUT"
run_verdict "$FIRED_CUT" issue-next "$PROMPT"
verdict_is yes "5 a Skill call naming the skill under test in a stream cut at the turn cap"

SIBLING_THEN_FIRED="$WORK/sibling-then-fired.jsonl"
{ init_event; skill_event issue-write; skill_event issue-next; result_event error_max_turns; } \
  > "$SIBLING_THEN_FIRED"
run_verdict "$SIBLING_THEN_FIRED" issue-next "$PROMPT"
verdict_is yes "6 the skill under test after a sibling in the same stream"

NAMELESS="$WORK/nameless.jsonl"
{ init_event; bare_skill_event; result_event error_max_turns; } > "$NAMELESS"
run_verdict "$NAMELESS" issue-next "$PROMPT"
verdict_is cut "7 a Skill call carrying no skill name in a stream cut at the turn cap"

summary
