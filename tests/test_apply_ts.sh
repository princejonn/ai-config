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
echo "file" > "$PROJ/file"
run_ts "$PROJ/file"
[ "$status" = 2 ]; check $? "2 a regular file as the folder exits 2"
run_ts "$PROJ/absent"
[ "$status" = 2 ]; check $? "2 an absent path as the folder exits 2"
grep -q '^usage: ' "$ERR"; check $? "2 an absent path as the folder prints usage on stderr"
[ "$(ls -A "$PROJ")" = file ]; check $? "2 a regular file or an absent path as the folder creates nothing"

run_ts "$PROJ" "$PROJ"
[ "$status" = 2 ]; check $? "3 two folders exit 2"
grep -q '^usage: ' "$ERR"; check $? "3 two folders print usage on stderr"
[ "$(ls -A "$PROJ")" = file ]; check $? "3 two folders create nothing"

fresh_project
run_ts --check "$PROJ"
[ "$status" = 1 ]; check $? "4 check on a folder without .claude exits 1"
grep -q "^  link: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "4 check on a folder without .claude reports the pending link"
! grep -q '^Applied to' "$OUT"; check $? "4 check on a folder without .claude prints no Applied line"
[ ! -e "$PROJ/.claude" ]; check $? "4 check on a folder without .claude creates no .claude"
[ ! -L "$PROJ/.claude" ]; check $? "4 check on a folder without .claude creates no .claude symlink"

run_ts "$PROJ"
[ "$status" = 0 ]; check $? "5 fresh apply exits 0"
links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md"; check $? "5 fresh apply links the rule"
grep -q "^  link: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "5 fresh apply reports the link"
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]; check $? "5 fresh apply ends with Applied to the folder"
[ ! -s "$ERR" ]; check $? "5 fresh apply prints nothing on stderr"

run_ts "$PROJ"
[ "$status" = 0 ]; check $? "6 second apply exits 0"
! grep -Eq '^  (link|adopt|prune|foreign):' "$OUT"; check $? "6 second apply changes nothing"
[ "$(grep -c '^  ok: ' "$OUT")" = 1 ]; check $? "6 second apply prints one ok line"
grep -q "^  ok: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "6 second apply prints ok for the rule"
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]; check $? "6 second apply ends with Applied to the folder"

run_ts --check "$PROJ"
[ "$status" = 0 ]; check $? "7 check after apply exits 0"
grep -q "^  ok: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "7 check after apply prints ok for the rule"
! grep -q '^Applied to' "$OUT"; check $? "7 check after apply prints no Applied line"

fresh_project
mkdir -p "$PROJ/.claude/rules"
cp "$RULESET/demo.md" "$PROJ/.claude/rules/demo.md"
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "8 byte-identical regular file: apply exits 0"
grep -q "^  adopt: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "8 byte-identical regular file is reported adopted"
links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md"; check $? "8 byte-identical regular file is adopted"

fresh_project
mkdir -p "$PROJ/.claude/rules"
echo "different" > "$PROJ/.claude/rules/demo.md"
run_ts "$PROJ"
[ "$status" = 1 ]; check $? "9 differing regular file: apply exits 1"
grep -q "^CONFLICT: $PROJ/.claude/rules/demo.md (content differs from $RULESET/demo.md)$" "$ERR"; check $? "9 differing regular file is a CONFLICT"
! grep -q '^Applied to' "$OUT"; check $? "9 differing regular file: apply prints no Applied line"
run_ts --check "$PROJ"
[ "$status" = 1 ]; check $? "9 differing regular file: check exits 1"
[ ! -L "$PROJ/.claude/rules/demo.md" ]; check $? "9 differing regular file is left unlinked"
[ "$(cat "$PROJ/.claude/rules/demo.md")" = "different" ]; check $? "9 differing regular file keeps its content"

fresh_project
run_ts "$PROJ"
echo "mine" > "$PROJ/.claude/rules/mine.md"
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "10 foreign file in .claude/rules: apply exits 0"
grep -q "^  foreign: $PROJ/.claude/rules/mine.md$" "$OUT"; check $? "10 foreign file in .claude/rules is reported"
run_ts --check "$PROJ"
[ "$status" = 1 ]; check $? "10 foreign file in .claude/rules: check exits 1"
[ "$(cat "$PROJ/.claude/rules/mine.md")" = "mine" ]; check $? "10 foreign file in .claude/rules keeps its content"

fresh_project
run_ts "$PROJ"
ln -s "$WORK/nowhere" "$PROJ/.claude/rules/elsewhere.md"
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "11 dangling symlink in .claude/rules: apply exits 0"
[ "$(readlink "$PROJ/.claude/rules/elsewhere.md")" = "$WORK/nowhere" ]; check $? "11 dangling symlink to outside the repo in .claude/rules is left alone"
grep -q "^  foreign: $PROJ/.claude/rules/elsewhere.md$" "$OUT"; check $? "11 dangling symlink to outside the repo in .claude/rules is reported foreign"
! grep -Eq '^  (link|prune|adopt): .*elsewhere\.md' "$OUT"; check $? "11 dangling symlink to outside the repo in .claude/rules is neither linked, pruned nor adopted"

fresh_project
mkdir -p "$PROJ/.claude"
ln -s "$WORK/nowhere" "$PROJ/.claude/settings.json"
ln -s "$WORK/nowhere" "$PROJ/link"
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "12 symlinks outside .claude/rules: apply exits 0"
run_ts --check "$PROJ"
[ "$status" = 0 ]; check $? "12 symlinks outside .claude/rules: check exits 0"
! grep -qF "$PROJ/.claude/settings.json" "$OUT"; check $? "12 a symlinked .claude/settings.json is not reported"
! grep -qF "$PROJ/link" "$OUT"; check $? "12 a symlink beside .claude is not reported"
[ "$(readlink "$PROJ/.claude/settings.json")" = "$WORK/nowhere" ]; check $? "12 a symlinked .claude/settings.json is not touched"
[ "$(readlink "$PROJ/link")" = "$WORK/nowhere" ]; check $? "12 a symlink beside .claude is not touched"

PROJ="$WORK/project with space"
mkdir -p "$PROJ"
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "13 folder path with a space: apply exits 0"
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]; check $? "13 folder path with a space ends with Applied to the folder"
run_ts --check "$PROJ"
[ "$status" = 0 ]; check $? "13 folder path with a space: check exits 0"
links_to "$PROJ/.claude/rules/demo.md" "$RULESET/demo.md"; check $? "13 folder path with a space is linked"

mkdir -p "$CWD/rel"
run_ts rel
[ "$status" = 0 ]; check $? "14 relative folder: apply exits 0"
links_to "$CWD/rel/.claude/rules/demo.md" "$RULESET/demo.md"; check $? "14 relative folder is resolved against the working directory"
[ "$(tail -n 1 "$OUT")" = "Applied to $CWD/rel." ]; check $? "14 relative folder is named absolute in the Applied line"

fresh_project
run_ts "$PROJ"
rm "$RULESET/demo.md"
run_ts --check "$PROJ"
[ "$status" = 1 ]; check $? "15 link to a removed set file: check exits 1"
grep -q "^  prune: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "15 link to a removed set file: check reports the pending prune"
[ -L "$PROJ/.claude/rules/demo.md" ]; check $? "15 link to a removed set file survives check"
run_ts "$PROJ"
[ "$status" = 0 ]; check $? "15 link to a removed set file: apply exits 0"
grep -q "^  prune: $PROJ/.claude/rules/demo.md -> $RULESET/demo.md$" "$OUT"; check $? "15 link to a removed set file: apply reports the prune"
[ ! -L "$PROJ/.claude/rules/demo.md" ]; check $? "15 link to a removed set file is pruned"
[ ! -e "$PROJ/.claude/rules/demo.md" ]; check $? "15 nothing is left where the removed set file was linked"
[ "$(tail -n 1 "$OUT")" = "Applied to $PROJ." ]; check $? "15 the pruning apply ends with Applied to the folder"

printf '%s\n' '---' 'paths: ["**/*.ts"]' '---' '# Demo' 'rule' > "$RULESET/demo.md"
fresh_project
ELSEWHERE="$WORK/elsewhere$projects"
mkdir -p "$ELSEWHERE" "$PROJ/.claude"
ln -s "$ELSEWHERE" "$PROJ/.claude/rules"
symlink_conflict() {
  local label="$1"
  shift
  run_ts "$@"
  [ "$status" = 1 ]; check $? "16 $label exits 1"
  grep -q "^CONFLICT: $SYMLINKED (symlink; links would land outside $PROJ)$" "$ERR"; check $? "16 $label is a CONFLICT"
  [ ! -s "$OUT" ]; check $? "16 $label prints nothing on stdout"
}
SYMLINKED="$PROJ/.claude/rules"
symlink_conflict "a symlinked .claude/rules in apply" "$PROJ"
symlink_conflict "a symlinked .claude/rules in check" --check "$PROJ"
[ -z "$(ls -A "$ELSEWHERE")" ]; check $? "16 nothing lands behind a symlinked .claude/rules"
fresh_project
ELSEWHERE2="$WORK/elsewhere$projects"
mkdir -p "$ELSEWHERE2"
ln -s "$ELSEWHERE2" "$PROJ/.claude"
SYMLINKED="$PROJ/.claude"
symlink_conflict "a symlinked .claude in apply" "$PROJ"
symlink_conflict "a symlinked .claude in check" --check "$PROJ"
[ -z "$(ls -A "$ELSEWHERE2")" ]; check $? "16 nothing lands behind a symlinked .claude"

summary
