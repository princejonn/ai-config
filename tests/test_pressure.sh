#!/bin/bash
set -u

SCRATCH=ai-config-pressure-test
. "$(dirname "$0")/lib.sh"

ERR="$WORK/err"
FAIL_DUMP="$ERR"
PROMPT='Tidy up the labels on the open issues.'
SLASH_PROMPT='/commit-item'
CONFIG="$WORK/config"
TRANSCRIPTS="$CONFIG/projects/-tmp-widget"
HOME_DIR="$WORK/home"
mkdir -p "$TRANSCRIPTS" "$HOME_DIR"

init_event() {
  printf '{"type":"system","subtype":"init","session_id":"%s"}\n' "${1:-pressure-fixture}"
}

text_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"text","text":"%s"}]}}\n' "$1"
}

skill_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"%s"}}]}}\n' "$1"
}

agent_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Agent","input":{"description":"lane","prompt":"%s","subagent_type":"%s"}}]}}\n' "${2:-brief}" "$1"
}

result_event() {
  printf '{"type":"result","subtype":"%s"}\n' "$1"
}

transcript_entry() {
  printf '{"type":"user","message":{"role":"user","content":"%s"}}\n' "$1"
}

verdict=""
status=0
run_verdict() {
  verdict="$(HOME="$HOME_DIR" CLAUDE_CONFIG_DIR="$CONFIG" /bin/bash "$HERE/pressure.sh" --verdict "$1" "$2" "$3" 2>"$ERR")"
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

EXPANDED="$WORK/expanded.jsonl"
{ init_event expanded-fixture; result_event success; } > "$EXPANDED"
transcript_entry '<command-name>/commit-item</command-name>' > "$TRANSCRIPTS/expanded-fixture.jsonl"
run_verdict "$EXPANDED" commit-item "$SLASH_PROMPT"
verdict_is yes "5 a /name prompt whose session transcript carries the expanded command"

for pair in researcher:research reviewer:review-change verifier:verify-claim; do
  agent="${pair%%:*}"
  skill="${pair##*:}"
  DEDICATED="$WORK/dedicated-$agent.jsonl"
  { init_event; agent_event "$agent"; result_event success; } > "$DEDICATED"
  run_verdict "$DEDICATED" "$skill" "$PROMPT"
  verdict_is yes "6 a dispatch to $agent, whose skills are exactly the skill under test"
done

ADDED="$WORK/added"
CLAUDE_CONFIG_DIR="$CONFIG" /bin/bash "$HERE/pressure.sh" --only test --dry-run > "$ADDED" 2>"$ERR"
check $? "7 --dry-run exits 0"
[ "$(grep -c "^  \(fire   \|no-fire\) claude -p '" "$ADDED")" = 4 ]; check $? "7 the prompt is the first argument after -p on every fire and no-fire line"
[ "$(grep -c -- "--max-turns 3 --add-dir '$HERE/../claude' '$CONFIG' </dev/null\$" "$ADDED")" = 4 ]; check $? "7 every fire and no-fire line ends with --add-dir on the config tree and the Claude config dir"
CLAUDE_CONFIG_DIR= HOME="$HOME_DIR" /bin/bash "$HERE/pressure.sh" --only test --dry-run > "$ADDED" 2>"$ERR"
[ "$(grep -c -- "--add-dir '$HERE/../claude' '$HOME_DIR/.claude' </dev/null\$" "$ADDED")" = 4 ]; check $? "7 an empty CLAUDE_CONFIG_DIR falls back to the Claude dir under HOME"

SHARED="$WORK/shared.jsonl"
{ init_event; agent_event tester 'Cover test_render_empty in a feature file with the author-gherkin skill, not the test skill.'; result_event error_max_turns; } > "$SHARED"
run_verdict "$SHARED" author-gherkin "$PROMPT"
verdict_is yes "8 a dispatch to tester, which claude/CLAUDE.md routes author-gherkin to, fires author-gherkin when its prompt names it before test"
run_verdict "$SHARED" test "$PROMPT"
verdict_is cut "8 a dispatch to tester fires no skill its prompt names after another skill tester preloads"
UNROUTED="$WORK/unrouted.jsonl"
{ init_event; agent_event developer 'Run the `diagnose-root-cause` skill on this brief.'; result_event error_max_turns; } > "$UNROUTED"
run_verdict "$UNROUTED" diagnose-root-cause "$PROMPT"
verdict_is cut "8 a dispatch to developer fires no skill claude/CLAUDE.md does not route to developer"

TREE="$WORK/tree"
mkdir -p "$TREE/tests" "$TREE/claude/skills/unpaired"
cp "$HERE/pressure.sh" "$TREE/tests/pressure.sh"
for skill in "$HERE"/../claude/skills/*/; do
  ln -s "$skill" "$TREE/claude/skills/$(basename "$skill")"
done
UNPAIRED="$WORK/unpaired"
/bin/bash "$TREE/tests/pressure.sh" --only test --dry-run > "$UNPAIRED" 2>"$ERR"
check $? "9 a skill directory without a prompt pair leaves --only on another skill running"
[ "$(grep -c '^test\(-2\)\{0,1\}$' "$UNPAIRED")" = 2 ]; check $? "9 --only test prints the test and test-2 pairs beside a skill directory without one"

summary
