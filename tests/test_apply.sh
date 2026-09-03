#!/bin/bash
set -u

HERE="$(cd "$(dirname "$0")" && pwd -P)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ai-config-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

FIX="$WORK/repo"
mkdir -p "$FIX/claude/skills/demo" "$FIX/claude/agents" "$FIX/claude/rules" "$FIX/claude/hooks" "$FIX/scripts"
cp "$HERE/../apply.sh" "$FIX/apply.sh"
cp "$HERE/../scripts/merge_settings.py" "$FIX/scripts/merge_settings.py"
echo "claude" > "$FIX/claude/CLAUDE.md"
echo "skill" > "$FIX/claude/skills/demo/SKILL.md"
echo "agent" > "$FIX/claude/agents/demo.md"
echo "rule" > "$FIX/claude/rules/demo.md"
echo "print('hook')" > "$FIX/claude/hooks/demo.py"
echo '{"PreToolUse": [{"matcher": "Bash", "script": "demo.py", "timeout": 10}]}' > "$FIX/claude/hooks.json"
FIX="$(cd "$FIX" && pwd -P)" || exit 1

pass=0
fail=0
check() {
  if [ "$1" = 0 ]; then echo "PASS $2"; pass=$((pass + 1)); else echo "FAIL $2"; fail=$((fail + 1)); fi
}

homes=0
fresh_home() {
  homes=$((homes + 1))
  HOME_DIR="$WORK/home$homes"
}

OUT="$WORK/out"
ERR="$WORK/err"
run_apply() {
  CLAUDE_CONFIG_DIR="$HOME_DIR" /bin/bash "$FIX/apply.sh" "$@" >"$OUT" 2>"$ERR"
  status=$?
}

links_to() { [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ]; }

all_linked() {
  links_to "$HOME_DIR/CLAUDE.md" "$FIX/claude/CLAUDE.md" \
    && links_to "$HOME_DIR/skills/demo" "$FIX/claude/skills/demo" \
    && links_to "$HOME_DIR/agents/demo.md" "$FIX/claude/agents/demo.md" \
    && links_to "$HOME_DIR/rules/demo.md" "$FIX/claude/rules/demo.md" \
    && links_to "$HOME_DIR/hooks/demo.py" "$FIX/claude/hooks/demo.py"
}

fresh_home
run_apply --check
[ "$status" = 1 ] && [ ! -e "$HOME_DIR" ] && [ ! -L "$HOME_DIR" ]
check $? "1 check on a nonexistent target exits 1 and leaves it absent"

run_apply
[ "$status" = 0 ] && all_linked \
  && grep -q '^Applied\. Restart Claude Code sessions to pick up changes\.$' "$OUT" \
  && python3 -c '
import json, sys
doc = json.load(open(sys.argv[1]))
group = doc["hooks"]["PreToolUse"][0]
assert group["matcher"] == "Bash"
assert group["hooks"] == [{"type": "command", "command": "python3 " + sys.argv[2] + "/hooks/demo.py", "timeout": 10}]
' "$HOME_DIR/settings.json" "$HOME_DIR"
check $? "2 fresh apply links every target, writes the demo hook and prints Applied"

cp "$HOME_DIR/settings.json" "$WORK/settings.before"
run_apply
[ "$status" = 0 ] && ! grep -Eq '^  (link|adopt|prune|foreign):' "$OUT" \
  && [ "$(grep -c '^  ok: ' "$OUT")" = 5 ] \
  && grep -q "^  ok: $HOME_DIR/CLAUDE.md -> $FIX/claude/CLAUDE.md$" "$OUT" \
  && grep -q "^  ok: $HOME_DIR/skills/demo -> $FIX/claude/skills/demo$" "$OUT" \
  && cmp -s "$WORK/settings.before" "$HOME_DIR/settings.json"
check $? "3 second apply changes nothing and prints ok for every target"

run_apply --check
[ "$status" = 0 ]
check $? "4 check after apply exits 0"

fresh_home
mkdir -p "$HOME_DIR/agents"
echo "different" > "$HOME_DIR/agents/demo.md"
run_apply
[ "$status" = 1 ] && grep -q "^CONFLICT: $HOME_DIR/agents/demo.md" "$ERR" && ! grep -q '^Applied\.' "$OUT" \
  && [ ! -L "$HOME_DIR/agents/demo.md" ] && [ "$(cat "$HOME_DIR/agents/demo.md")" = "different" ] \
  && links_to "$HOME_DIR/CLAUDE.md" "$FIX/claude/CLAUDE.md" \
  && links_to "$HOME_DIR/skills/demo" "$FIX/claude/skills/demo" \
  && links_to "$HOME_DIR/rules/demo.md" "$FIX/claude/rules/demo.md" \
  && links_to "$HOME_DIR/hooks/demo.py" "$FIX/claude/hooks/demo.py"
check $? "5 differing regular file is a CONFLICT without Applied and the rest is still linked"

fresh_home
mkdir -p "$HOME_DIR/rules"
cp "$FIX/claude/rules/demo.md" "$HOME_DIR/rules/demo.md"
run_apply
[ "$status" = 0 ] && grep -q "^  adopt: $HOME_DIR/rules/demo.md -> $FIX/claude/rules/demo.md$" "$OUT" \
  && links_to "$HOME_DIR/rules/demo.md" "$FIX/claude/rules/demo.md"
check $? "6 identical regular file is adopted"

fresh_home
mkdir -p "$HOME_DIR/skills"
cp -R "$FIX/claude/skills/demo" "$HOME_DIR/skills/demo"
run_apply
[ "$status" = 0 ] && grep -q "^  adopt: $HOME_DIR/skills/demo -> $FIX/claude/skills/demo$" "$OUT" \
  && links_to "$HOME_DIR/skills/demo" "$FIX/claude/skills/demo" \
  && [ ! -e "$FIX/claude/skills/demo/demo" ] && [ ! -L "$FIX/claude/skills/demo/demo" ] \
  && [ "$(cat "$FIX/claude/skills/demo/SKILL.md")" = "skill" ]
check $? "7 identical directory is adopted with nothing nested"

fresh_home
mkdir -p "$HOME_DIR/skills"
echo "x" > "$HOME_DIR/skills/demo"
run_apply
[ "$status" = 1 ] && grep -q "^CONFLICT: $HOME_DIR/skills/demo" "$ERR" \
  && [ ! -L "$HOME_DIR/skills/demo" ] && [ "$(cat "$HOME_DIR/skills/demo")" = "x" ]
check $? "8 regular file at a skill target is a CONFLICT"

fresh_home
mkdir -p "$HOME_DIR/rules"
ln -s /etc/hosts "$HOME_DIR/rules/demo.md"
run_apply
[ "$status" = 1 ] && grep -q "^CONFLICT: $HOME_DIR/rules/demo.md" "$ERR" \
  && [ "$(readlink "$HOME_DIR/rules/demo.md")" = /etc/hosts ]
check $? "9 foreign symlink at an owned target is a CONFLICT and left alone"

fresh_home
mkdir -p "$HOME_DIR/agents" "$HOME_DIR/skills"
ln -s "$FIX/claude/rules/demo.md" "$HOME_DIR/agents/demo.md"
ln -s "$FIX/claude" "$HOME_DIR/skills/demo"
run_apply
[ "$status" = 0 ] && ! grep -q '^CONFLICT' "$ERR" && all_linked \
  && grep -q "^  link: $HOME_DIR/agents/demo.md -> $FIX/claude/agents/demo.md$" "$OUT" \
  && grep -q "^  link: $HOME_DIR/skills/demo -> $FIX/claude/skills/demo$" "$OUT" \
  && [ ! -e "$FIX/claude/demo" ] && [ ! -L "$FIX/claude/demo" ]
check $? "10 links elsewhere under the repo are relinked for a file and a directory"

fresh_home
mkdir -p "$HOME_DIR/agents" "$HOME_DIR/rules"
ln -s ../../repo/claude/agents/demo.md "$HOME_DIR/agents/demo.md"
ln -s ../../repo/claude/agents/demo.md "$HOME_DIR/rules/demo.md"
run_apply
[ "$status" = 0 ] && ! grep -q '^CONFLICT' "$ERR" && ! grep -q '^  foreign:' "$OUT" \
  && grep -q "^  ok: $HOME_DIR/agents/demo.md -> $FIX/claude/agents/demo.md$" "$OUT" \
  && [ "$(readlink "$HOME_DIR/agents/demo.md")" = ../../repo/claude/agents/demo.md ] \
  && grep -q "^  link: $HOME_DIR/rules/demo.md -> $FIX/claude/rules/demo.md$" "$OUT" \
  && links_to "$HOME_DIR/rules/demo.md" "$FIX/claude/rules/demo.md"
check $? "11 relative link into the repo is ok when exact and relinked otherwise"

fresh_home
mkdir -p "$HOME_DIR/agents" "$HOME_DIR/hooks"
ln -s ../../repo/./claude/agents/demo.md "$HOME_DIR/agents/demo.md"
ln -s "$FIX//claude/hooks//demo.py" "$HOME_DIR/hooks/demo.py"
run_apply
[ "$status" = 0 ] && ! grep -q '^CONFLICT' "$ERR" && ! grep -q '^  foreign:' "$OUT" \
  && grep -q "^  ok: $HOME_DIR/agents/demo.md -> $FIX/claude/agents/demo.md$" "$OUT" \
  && grep -q "^  ok: $HOME_DIR/hooks/demo.py -> $FIX/claude/hooks/demo.py$" "$OUT" \
  && [ "$(readlink "$HOME_DIR/agents/demo.md")" = ../../repo/./claude/agents/demo.md ] \
  && [ "$(readlink "$HOME_DIR/hooks/demo.py")" = "$FIX//claude/hooks//demo.py" ]
check $? "12 link targets with a dot segment or doubled slash are ok"

fresh_home
run_apply
echo "other" > "$HOME_DIR/skills/other.md"
run_apply
apply_status=$status
grep -q "^  foreign: $HOME_DIR/skills/other.md$" "$OUT"
foreign_reported=$?
run_apply --check
[ "$apply_status" = 0 ] && [ "$foreign_reported" = 0 ] && [ "$status" = 1 ] && [ -f "$HOME_DIR/skills/other.md" ]
check $? "13 foreign regular file is reported and fails check"

fresh_home
run_apply
ln -s /etc/hosts "$HOME_DIR/hooks/x.py"
run_apply
[ "$status" = 0 ] && [ "$(readlink "$HOME_DIR/hooks/x.py")" = /etc/hosts ] \
  && grep -q "^  foreign: $HOME_DIR/hooks/x.py$" "$OUT" && ! grep -Eq '^  (link|prune|adopt): .*x\.py' "$OUT"
check $? "14 foreign symlink in an owned dir is left alone and reported"

fresh_home
run_apply
ln -s "$FIX/claude/rules/demo.md" "$HOME_DIR/agents/other.md"
run_apply
apply_status=$status
grep -q "^  foreign: $HOME_DIR/agents/other.md$" "$OUT"
foreign_reported=$?
run_apply --check
[ "$apply_status" = 0 ] && [ "$foreign_reported" = 0 ] && [ "$status" = 1 ] \
  && [ "$(readlink "$HOME_DIR/agents/other.md")" = "$FIX/claude/rules/demo.md" ]
check $? "15 link to another repo path in an owned dir is foreign and fails check"

fresh_home
run_apply
rm -r "$FIX/claude/skills/demo"
run_apply
[ "$status" = 0 ] && grep -q "^  prune: $HOME_DIR/skills/demo -> $FIX/claude/skills/demo$" "$OUT" \
  && [ ! -L "$HOME_DIR/skills/demo" ] && [ ! -e "$HOME_DIR/skills/demo" ]
check $? "16 dangling owned link is pruned"

echo "PASS $pass FAIL $fail"
[ "$fail" = 0 ]
