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
mkdir -p "$TRANSCRIPTS"
HOME_DIR="$WORK/home"
for agents in "$CONFIG/agents" "$HOME_DIR/.claude/agents"; do
  mkdir -p "$agents"
  printf '%s\n' '---' 'name: scout' 'skills: [research]' '---' > "$agents/scout.md"
done

init_event() {
  printf '{"type":"system","subtype":"init","session_id":"%s"}\n' "${1:-pressure-fixture}"
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

agent_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Agent","input":{"description":"lane","prompt":"brief","subagent_type":"%s"}}]}}\n' "$1"
}

untyped_agent_event() {
  printf '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Agent","input":{"description":"lane","prompt":"brief"}}]}}\n'
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
  verdict="$(HOME="$HOME_DIR" CLAUDE_CONFIG_DIR="$CONFIG" /bin/bash "${4:-$HERE/pressure.sh}" --verdict "$1" "$2" "$3" 2>"$ERR")"
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

EXPANDED="$WORK/expanded.jsonl"
{ init_event expanded-fixture; result_event success; } > "$EXPANDED"
transcript_entry '<command-name>/commit-item</command-name>' > "$TRANSCRIPTS/expanded-fixture.jsonl"
run_verdict "$EXPANDED" commit-item "$SLASH_PROMPT"
verdict_is yes "8 a /name prompt whose session transcript carries the expanded command"

UNEXPANDED="$WORK/unexpanded.jsonl"
{ init_event unexpanded-fixture; result_event success; } > "$UNEXPANDED"
transcript_entry 'show me the git status' > "$TRANSCRIPTS/unexpanded-fixture.jsonl"
run_verdict "$UNEXPANDED" commit-item "$SLASH_PROMPT"
verdict_is no "9 a /name prompt whose session transcript lacks the expanded command"

DRY="$WORK/dry"
/bin/bash "$HERE/pressure.sh" --only test --dry-run > "$DRY" 2>"$ERR"
check $? "10 --only on a skill carrying several pairs exits 0"
[ "$(grep -c '^test' "$DRY")" = 2 ]; check $? "10 --only runs every pair the skill carries"
grep -q '^test$' "$DRY"; check $? "10 the first pair of a skill keeps the bare name"
grep -q '^test-2$' "$DRY"; check $? "10 a later pair is tagged by its ordinal"

/bin/bash "$HERE/pressure.sh" --only ghost --dry-run > "$DRY" 2>"$ERR"
[ "$?" = 2 ]; check $? "11 --only naming no pair exits 2"
grep -q '^pressure: no prompt pair named ghost$' "$ERR"; check $? "11 --only naming no pair says which"

for agent in researcher-trivial researcher researcher-complex; do
  DEDICATED="$WORK/dedicated-$agent.jsonl"
  { init_event; agent_event "$agent"; result_event success; } > "$DEDICATED"
  run_verdict "$DEDICATED" research "$PROMPT"
  verdict_is yes "12 a dispatch to $agent, whose skills are exactly the skill under test"
done

DEDICATED_SIBLING="$WORK/dedicated-sibling.jsonl"
{ init_event; agent_event researcher-trivial; result_event error_max_turns; } > "$DEDICATED_SIBLING"
run_verdict "$DEDICATED_SIBLING" verify-claim "$PROMPT"
verdict_is no "13 a dispatch to an agent whose skills are exactly a sibling, in a stream cut at the turn cap"

SHARED="$WORK/shared.jsonl"
{ init_event; agent_event developer; result_event error_max_turns; } > "$SHARED"
for skill in implement test diagnose-root-cause author-gherkin; do
  run_verdict "$SHARED" "$skill" "$PROMPT"
  verdict_is cut "14 a dispatch to developer, which carries several skills, fires none of them: $skill"
done

for agent in general-purpose Explore Plan; do
  BUILT_IN="$WORK/built-in-$agent.jsonl"
  { init_event; agent_event "$agent"; result_event error_max_turns; } > "$BUILT_IN"
  run_verdict "$BUILT_IN" research "$PROMPT"
  verdict_is cut "15 a dispatch to $agent, which has no file in the tree's agents, fires no skill"
done

DECOY="$WORK/decoy.jsonl"
{ init_event; agent_event scout; result_event error_max_turns; } > "$DECOY"
run_verdict "$DECOY" research "$PROMPT"
verdict_is cut "16 an agent's skills are read from the tree, never from the config dir or ~/.claude"

TREE="$WORK/tree"
mkdir -p "$TREE/tests" "$TREE/claude/agents"
cp "$HERE/pressure.sh" "$TREE/tests/pressure.sh"
ln -s "$HERE/../claude/skills" "$TREE/claude/skills"
printf '%s\n' '---' 'name: lookout' '---' '' 'skills: [research]' > "$TREE/claude/agents/lookout.md"
BODY="$WORK/body.jsonl"
{ init_event; agent_event lookout; result_event error_max_turns; } > "$BODY"
run_verdict "$BODY" research "$PROMPT" "$TREE/tests/pressure.sh"
verdict_is cut "17 an agent's skills are read from its frontmatter, never from its body"

UNTYPED="$WORK/untyped.jsonl"
{ init_event; untyped_agent_event; result_event error_max_turns; } > "$UNTYPED"
run_verdict "$UNTYPED" research "$PROMPT"
verdict_is cut "18 an Agent call carrying no subagent type in a stream cut at the turn cap"

summary
