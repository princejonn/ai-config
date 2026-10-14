#!/bin/bash
set -u

SCRATCH=ai-config-ts-test
. "$(dirname "$0")/lib.sh"

FIX="$WORK/repo"
RULESET="$FIX/claude/rulesets/typescript"
mkdir -p "$FIX/lib" "$RULESET"
cp "$HERE/../apply-ts.sh" "$FIX/apply-ts.sh"
cp "$HERE/../lib/links.sh" "$FIX/lib/links.sh"
printf '%s\n' '---' 'paths: ["**/*.ts"]' '---' '# Demo' 'rule' > "$RULESET/demo.md"

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

run_ts
[ "$status" = 2 ]; check $? "1 no folder exits 2"
grep -q '^usage: ' "$ERR"; check $? "1 no folder prints usage on stderr"
run_ts --check
[ "$status" = 2 ]; check $? "1 no folder with --check exits 2"
grep -q '^usage: ' "$ERR"; check $? "1 no folder with --check prints usage on stderr"
[ ! -s "$OUT" ]; check $? "1 no folder prints nothing on stdout"
[ -z "$(ls -A "$CWD")" ]; check $? "1 no folder creates nothing"

fresh_project
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "2 fresh apply exits 0"
links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md"; check $? "2 fresh apply links the rule"
grep -q "^  link: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "2 fresh apply reports the link"
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]; check $? "2 fresh apply ends with Applied to the folder"
[ ! -s "$ERR" ]; check $? "2 fresh apply prints nothing on stderr"

run_ts "$PROJ"
[ "$status" = 0 ]; check $? "3 second apply exits 0"
! grep -Eq '^  (link|adopt|prune|foreign):' "$OUT"; check $? "3 second apply changes nothing"
[ "$(grep -c '^  ok: ' "$OUT")" = 1 ]; check $? "3 second apply prints one ok line"
grep -q "^  ok: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "3 second apply prints ok for the rule"
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]; check $? "3 second apply ends with Applied to the folder"

run_ts --check "$PROJ"
[ "$status" = 0 ]; check $? "4 check after apply exits 0"
grep -q "^  ok: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "4 check after apply prints ok for the rule"
! grep -q '^Applied to' "$OUT"; check $? "4 check after apply prints no Applied line"

fresh_project
mkdir -p "$PROJ/.claude/rules"
echo "different" > "$PROJ/.claude/rules/demo.md"
run_ts "$PROJ"
[ "$status" = 1 ]; check $? "5 differing regular file: apply exits 1"
grep -q "^CONFLICT: $PROJ/.claude/rules/demo.md (content differs from $RULESET/demo.md)$" "$ERR"; check $? "5 differing regular file is a CONFLICT"
! grep -q '^Applied to' "$OUT"; check $? "5 differing regular file: apply prints no Applied line"
run_ts --check "$PROJ"
[ "$status" = 1 ]; check $? "5 differing regular file: check exits 1"
[ ! -L "$PROJ/.claude/rules/demo.md" ]; check $? "5 differing regular file is left unlinked"
[ "$(cat "$PROJ/.claude/rules/demo.md")" = "different" ]; check $? "5 differing regular file keeps its content"

fresh_project
ELSEWHERE="$WORK/elsewhere$projects"
mkdir -p "$ELSEWHERE" "$PROJ/.claude"
ln -s "$ELSEWHERE" "$PROJ/.claude/rules"
symlink_conflict() {
  local label="$1"
  shift
  run_ts "$@"
  [ "$status" = 1 ]; check $? "6 $label exits 1"
  grep -q "^CONFLICT: $SYMLINKED (symlink; links would land outside $PROJ)$" "$ERR"; check $? "6 $label is a CONFLICT"
  [ ! -s "$OUT" ]; check $? "6 $label prints nothing on stdout"
}
SYMLINKED="$PROJ/.claude/rules"
symlink_conflict "a symlinked .claude/rules in apply" "$PROJ"
symlink_conflict "a symlinked .claude/rules in check" --check "$PROJ"
[ -z "$(ls -A "$ELSEWHERE")" ]; check $? "6 nothing lands behind a symlinked .claude/rules"
fresh_project
ELSEWHERE2="$WORK/elsewhere$projects"
mkdir -p "$ELSEWHERE2"
ln -s "$ELSEWHERE2" "$PROJ/.claude"
SYMLINKED="$PROJ/.claude"
symlink_conflict "a symlinked .claude in apply" "$PROJ"
symlink_conflict "a symlinked .claude in check" --check "$PROJ"
[ -z "$(ls -A "$ELSEWHERE2")" ]; check $? "6 nothing lands behind a symlinked .claude"

summary
