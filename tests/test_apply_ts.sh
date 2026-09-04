#!/bin/bash
set -u

HERE="$(cd "$(dirname "$0")" && pwd -P)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ai-config-ts-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
WORK="$(cd "$WORK" && pwd -P)" || exit 1

FIX="$WORK/repo"
RULESET="$FIX/claude/rulesets/typescript"
mkdir -p "$FIX/lib" "$RULESET"
cp "$HERE/../apply-ts.sh" "$FIX/apply-ts.sh"
cp "$HERE/../lib/links.sh" "$FIX/lib/links.sh"
printf '%s\n' '---' 'paths: ["**/*.ts"]' '---' '# Demo' 'rule' > "$RULESET/demo.md"

pass=0
fail=0
check() {
  if [ "$1" = 0 ]; then echo "PASS $2"; pass=$((pass + 1)); else echo "FAIL $2"; fail=$((fail + 1)); fi
}

projects=0
fresh_project() {
  projects=$((projects + 1))
  PROJ="$WORK/project$projects"
  mkdir -p "$PROJ"
}

CWD="$WORK/cwd"
mkdir -p "$CWD"
OUT="$WORK/out"
ERR="$WORK/err"
run_ts() {
  (cd "$CWD" && /bin/bash "$FIX/apply-ts.sh" "$@") >"$OUT" 2>"$ERR"
  status=$?
}

links_to() { [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ]; }

run_ts
no_arg_status=$status
grep -q '^usage: ' "$ERR"
no_arg_usage=$?
run_ts --check
[ "$no_arg_status" = 2 ] && [ "$no_arg_usage" = 0 ] && [ "$status" = 2 ] && grep -q '^usage: ' "$ERR" \
  && [ ! -s "$OUT" ] && [ -z "$(ls -A "$CWD")" ]
check $? "1 no folder, with or without --check, prints usage on stderr, exits 2 and creates nothing"

fresh_project
echo "file" > "$PROJ/file"
run_ts "$PROJ/file"
file_status=$status
run_ts "$PROJ/absent"
[ "$file_status" = 2 ] && [ "$status" = 2 ] && grep -q '^usage: ' "$ERR" && [ "$(ls -A "$PROJ")" = file ]
check $? "2 a regular file or an absent path as the folder exits 2 and creates nothing"

run_ts "$PROJ" "$PROJ"
[ "$status" = 2 ] && grep -q '^usage: ' "$ERR" && [ "$(ls -A "$PROJ")" = file ]
check $? "3 two folders exit 2 and create nothing"

fresh_project
run_ts --check "$PROJ"
[ "$status" = 1 ] && grep -q "^  link: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT" \
  && ! grep -q '^Applied to' "$OUT" && [ ! -e "$PROJ/.claude" ] && [ ! -L "$PROJ/.claude" ]
check $? "4 check on a folder without .claude exits 1, reports the pending link and creates nothing"

run_ts "$PROJ"
[ "$status" = 0 ] && links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md" \
  && grep -q "^  link: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT" \
  && [ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ] && [ ! -s "$ERR" ]
check $? "5 fresh apply links the rule and ends with Applied to the folder"

run_ts "$PROJ"
[ "$status" = 0 ] && ! grep -Eq '^  (link|adopt|prune|foreign):' "$OUT" \
  && [ "$(grep -c '^  ok: ' "$OUT")" = 1 ] \
  && grep -q "^  ok: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT" \
  && [ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]
check $? "6 second apply changes nothing and prints ok"

run_ts --check "$PROJ"
[ "$status" = 0 ] && grep -q "^  ok: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT" \
  && ! grep -q '^Applied to' "$OUT"
check $? "7 check after apply exits 0 without an Applied line"

fresh_project
mkdir -p "$PROJ/.claude/rules"
cp "$RULESET/demo.md" "$PROJ/.claude/rules/demo.md"
run_ts "$PROJ"
[ "$status" = 0 ] && grep -q "^  adopt: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT" \
  && links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md"
check $? "8 byte-identical regular file is adopted"

fresh_project
mkdir -p "$PROJ/.claude/rules"
echo "different" > "$PROJ/.claude/rules/demo.md"
run_ts "$PROJ"
apply_status=$status
grep -q "^CONFLICT: $PROJ/.claude/rules/demo.md (content differs from $RULESET/demo.md)$" "$ERR"
conflict_reported=$?
grep -q '^Applied to' "$OUT"
applied_printed=$?
run_ts --check "$PROJ"
[ "$apply_status" = 1 ] && [ "$conflict_reported" = 0 ] && [ "$applied_printed" = 1 ] && [ "$status" = 1 ] \
  && [ ! -L "$PROJ/.claude/rules/demo.md" ] && [ "$(cat "$PROJ/.claude/rules/demo.md")" = "different" ]
check $? "9 differing regular file is a CONFLICT left untouched; apply and check exit 1 without Applied"

fresh_project
run_ts "$PROJ"
echo "mine" > "$PROJ/.claude/rules/mine.md"
run_ts "$PROJ"
apply_status=$status
grep -q "^  foreign: $PROJ/.claude/rules/mine.md$" "$OUT"
foreign_reported=$?
run_ts --check "$PROJ"
[ "$apply_status" = 0 ] && [ "$foreign_reported" = 0 ] && [ "$status" = 1 ] \
  && [ "$(cat "$PROJ/.claude/rules/mine.md")" = "mine" ]
check $? "10 foreign file in .claude/rules is reported; apply exits 0 and check exits 1"

fresh_project
run_ts "$PROJ"
ln -s "$WORK/nowhere" "$PROJ/.claude/rules/elsewhere.md"
run_ts "$PROJ"
[ "$status" = 0 ] && [ "$(readlink "$PROJ/.claude/rules/elsewhere.md")" = "$WORK/nowhere" ] \
  && grep -q "^  foreign: $PROJ/.claude/rules/elsewhere.md$" "$OUT" \
  && ! grep -Eq '^  (link|prune|adopt): .*elsewhere\.md' "$OUT"
check $? "11 dangling symlink to outside the repo in .claude/rules is reported foreign and left alone"

fresh_project
mkdir -p "$PROJ/.claude"
ln -s "$WORK/nowhere" "$PROJ/.claude/settings.json"
ln -s "$WORK/nowhere" "$PROJ/link"
run_ts "$PROJ"
apply_status=$status
run_ts --check "$PROJ"
[ "$apply_status" = 0 ] && [ "$status" = 0 ] \
  && ! grep -qF "$PROJ/.claude/settings.json" "$OUT" && ! grep -qF "$PROJ/link" "$OUT" \
  && [ "$(readlink "$PROJ/.claude/settings.json")" = "$WORK/nowhere" ] && [ "$(readlink "$PROJ/link")" = "$WORK/nowhere" ]
check $? "12 symlinks outside .claude/rules are neither reported nor touched"

PROJ="$WORK/project with space"
mkdir -p "$PROJ"
run_ts "$PROJ"
apply_status=$status
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]
applied_printed=$?
run_ts --check "$PROJ"
[ "$apply_status" = 0 ] && [ "$applied_printed" = 0 ] && [ "$status" = 0 ] \
  && links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md"
check $? "13 folder path with a space is applied and checks clean"

mkdir -p "$CWD/rel"
run_ts rel
[ "$status" = 0 ] && links_to "$CWD/rel/.claude/rules/demo.md" "$RULESET/demo.md" \
  && [ "$(tail -n 1 "$OUT")" = "Applied to $CWD/rel." ]
check $? "14 relative folder is resolved against the working directory"

fresh_project
run_ts "$PROJ"
rm "$RULESET/demo.md"
run_ts --check "$PROJ"
check_status=$status
grep -q "^  prune: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"
prune_reported=$?
[ -L "$PROJ/.claude/rules/demo.md" ]
still_linked=$?
run_ts "$PROJ"
[ "$check_status" = 1 ] && [ "$prune_reported" = 0 ] && [ "$still_linked" = 0 ] && [ "$status" = 0 ] \
  && grep -q "^  prune: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT" \
  && [ ! -L "$PROJ/.claude/rules/demo.md" ] && [ ! -e "$PROJ/.claude/rules/demo.md" ] \
  && [ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]
check $? "15 link to a removed set file fails check and is pruned on the next apply"

printf '%s\n' '---' 'paths: ["**/*.ts"]' '---' '# Demo' 'rule' > "$RULESET/demo.md"
fresh_project
ELSEWHERE="$WORK/elsewhere$projects"
mkdir -p "$ELSEWHERE" "$PROJ/.claude"
ln -s "$ELSEWHERE" "$PROJ/.claude/rules"
symlink_conflict() {
  run_ts "$@"
  [ "$status" = 1 ] && grep -q "^CONFLICT: $SYMLINKED (symlink; links would land outside $PROJ)$" "$ERR" && [ ! -s "$OUT" ]
}
SYMLINKED="$PROJ/.claude/rules"
symlink_conflict "$PROJ"
rules_apply=$?
symlink_conflict --check "$PROJ"
rules_check=$?
rules_empty=$([ -z "$(ls -A "$ELSEWHERE")" ]; echo $?)
fresh_project
ELSEWHERE2="$WORK/elsewhere$projects"
mkdir -p "$ELSEWHERE2"
ln -s "$ELSEWHERE2" "$PROJ/.claude"
SYMLINKED="$PROJ/.claude"
symlink_conflict "$PROJ"
claude_apply=$?
symlink_conflict --check "$PROJ"
claude_check=$?
[ "$rules_apply" = 0 ] && [ "$rules_check" = 0 ] && [ "$rules_empty" = 0 ] \
  && [ "$claude_apply" = 0 ] && [ "$claude_check" = 0 ] && [ -z "$(ls -A "$ELSEWHERE2")" ]
check $? "16 a symlinked .claude or .claude/rules is a conflict in apply and check and nothing lands behind it"

echo "PASS $pass FAIL $fail"
[ "$fail" = 0 ]
