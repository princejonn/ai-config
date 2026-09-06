#!/bin/bash
set -u

SCRATCH=ai-config-so-test
. "$(dirname "$0")/lib.sh"

SCRIPT="$HERE/../bin/second-opinion-codex"

export FAKE_DIR="$WORK"
mkdir -p "$WORK/bin"
cat > "$WORK/bin/codex" <<'FAKE'
#!/bin/bash
cat > "$FAKE_DIR/stdin"
printf '%s\n' "$*" > "$FAKE_DIR/argv"
printf '%s\n' "${CODEX_CA_CERTIFICATE-unset}" > "$FAKE_DIR/ca"
printf 'call\n' >> "$FAKE_DIR/calls"
: > "$FAKE_DIR/ran"
cat "$FAKE_DIR/fake.stdout"
cat "$FAKE_DIR/fake.stderr" >&2
exit "$(cat "$FAKE_DIR/fake.status")"
FAKE
chmod +x "$WORK/bin/codex"

PACKET="$WORK/packet"
OPINION="$WORK/opinion"
OUT="$WORK/out"
ERR="$WORK/err"

fake_codex() {
  printf '%s\n' "$1" > "$WORK/fake.status"
  printf '%s' "$2" > "$WORK/fake.stdout"
  printf '%s' "$3" > "$WORK/fake.stderr"
}

write_packet() {
  printf '%s\n' "$@" > "$PACKET"
}

run_so() {
  rm -f "$WORK/ran" "$WORK/calls" "$WORK/stdin" "$WORK/argv" "$WORK/ca" "$OPINION" "$OPINION.stderr"
  PATH="$WORK/bin:$PATH" /bin/bash "$SCRIPT" "$@" >"$OUT" 2>"$ERR"
  status=$?
}

preamble() {
  local packet_lines prepended
  [ -f "$WORK/stdin" ] || return 1
  packet_lines="$(lines "$PACKET")"
  prepended=$(( $(lines "$WORK/stdin") - packet_lines ))
  [ "$prepended" -gt 0 ] || return 1
  tail -n "$packet_lines" "$WORK/stdin" | cmp -s - "$PACKET" || return 1
  head -n "$prepended" "$WORK/stdin"
}

usage_exit() {
  local label="$1"
  shift
  run_so "$@"
  [ "$status" = 2 ]; check $? "9 $label exits 2"
  [ ! -s "$OUT" ]; check $? "9 $label prints nothing on stdout"
  grep -q '^usage: ' "$ERR"; check $? "9 $label prints a usage line"
  [ ! -e "$WORK/ran" ]; check $? "9 $label never calls codex"
}

cannot_write_exit() {
  local label="$1" out="$2"
  run_so diff --packet "$PACKET" --out "$out"
  [ "$status" = 2 ]; check $? "10 an --out in $label exits 2"
  [ ! -s "$OUT" ]; check $? "10 an --out in $label prints nothing on stdout"
  [ ! -e "$WORK/ran" ]; check $? "10 an --out in $label never calls codex"
  [ "$(cat "$ERR")" = "second-opinion: cannot write $out" ]; check $? "10 an --out in $label names the file it cannot write"
}

available_run() {
  fake_codex 0 "$1" "$2"
  run_so diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 0 ]; check $? "11 codex exiting 0 with findings and the stderr line $2 exits 0"
  [ ! -s "$OUT" ]; check $? "11 codex exiting 0 with findings and the stderr line $2 prints nothing on stdout"
  [ ! -s "$ERR" ]; check $? "11 codex exiting 0 with findings and the stderr line $2 prints nothing on stderr"
  [ "$(cat "$OPINION")" = "$1" ]; check $? "11 codex exiting 0 with findings and the stderr line $2 puts the codex stdout verbatim in --out"
  [ "$(cat "$OPINION.stderr")" = "$2" ]; check $? "11 codex exiting 0 with findings and the stderr line $2 keeps the transcript in --out.stderr"
}

fake_codex 0 "P1 lib/links.sh:12 the mechanism" "sandbox: read-only"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ]; check $? "1 diff exits 0"
[ ! -s "$OUT" ]; check $? "1 diff prints nothing on stdout"
[ ! -s "$ERR" ]; check $? "1 diff prints nothing on stderr"
[ "$(cat "$OPINION")" = "P1 lib/links.sh:12 the mechanism" ]; check $? "1 diff fills --out with the codex stdout"
[ "$(cat "$OPINION.stderr")" = "sandbox: read-only" ]; check $? "1 diff fills --out.stderr with the codex stderr"
[ "$(cat "$WORK/ca")" = /etc/ssl/cert.pem ]; check $? "1 diff calls codex with the certificate set"
grep -q -F -- 'exec -s read-only --ignore-user-config -' "$WORK/argv"; check $? "1 diff calls codex read-only"
[ -n "$(preamble | tr -d '[:space:]')" ]; check $? "1 diff prepends the contract paragraph before the packet"
tail -n "$(lines "$PACKET")" "$WORK/stdin" | cmp -s - "$PACKET"; check $? "1 diff passes the packet verbatim"

fake_codex 7 "" 'stream error: unexpected status 500
retrying in 1s'
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ]; check $? "2 a non-zero codex exit exits 1"
[ ! -s "$OUT" ]; check $? "2 a non-zero codex exit prints nothing on stdout"
[ "$(cat "$ERR")" = "second-opinion unavailable: stream error: unexpected status 500" ]; check $? "2 a non-zero codex exit is unavailable with the first stderr line"
[ "$(lines "$WORK/calls")" = 1 ]; check $? "2 a non-zero codex exit calls codex exactly once"
[ ! -e "$OPINION" ]; check $? "2 a non-zero codex exit leaves no --out"
[ -s "$OPINION.stderr" ]; check $? "2 a non-zero codex exit keeps the transcript"

fake_codex 0 "" "model returned no message"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ]; check $? "3 empty codex stdout exits 1 although codex exited 0"
[ ! -s "$OUT" ]; check $? "3 empty codex stdout prints nothing on stdout"
[ "$(cat "$ERR")" = "second-opinion unavailable: model returned no message" ]; check $? "3 empty codex stdout is unavailable with the stderr line"
[ ! -e "$OPINION" ]; check $? "3 empty codex stdout leaves no --out"

for phrase in "You've hit your usage limit." "Not logged in" "Login is required to continue" \
  "quota exceeded" "rate limit exceeded"; do
  fake_codex 0 "" "sandbox: read-only
$phrase"
  run_so diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 1 ]; check $? "4 $phrase below the first transcript line exits 1"
  [ "$(cat "$ERR")" = "second-opinion unavailable: $phrase" ]; check $? "4 $phrase below the first transcript line is the reason, not the first line"
  [ "$(lines "$WORK/calls")" = 1 ]; check $? "4 $phrase below the first transcript line calls codex exactly once"
  [ ! -e "$OPINION" ]; check $? "4 $phrase below the first transcript line leaves no --out"
done

fake_codex 0 "P1 a finding" ""
rm -f "$WORK/ran"
PATH=/usr/bin:/bin /bin/bash "$SCRIPT" diff --packet "$PACKET" --out "$OPINION" >"$OUT" 2>"$ERR"
status=$?
[ "$status" = 1 ]; check $? "5 codex absent from PATH exits 1"
[ ! -s "$OUT" ]; check $? "5 codex absent from PATH prints nothing on stdout"
[ "$(lines "$ERR")" = 1 ]; check $? "5 codex absent from PATH prints one line on stderr"
grep -q '^second-opinion unavailable: ' "$ERR"; check $? "5 codex absent from PATH is unavailable"
[ ! -e "$WORK/ran" ]; check $? "5 codex absent from PATH never calls codex"
[ ! -e "$OPINION" ]; check $? "5 codex absent from PATH leaves no --out"

for token in "+++ b/.env" "+++ b/.env.local" "-----BEGIN OPENSSH PRIVATE KEY" "cp id_rsa /tmp/k" \
  "cp my_id_rsa /tmp/k" "id_ed25519.pub" "cat ~/.ssh/config" "/Users/x/.ssh/known_hosts" \
  "cat .ssh/config"; do
  write_packet "diff --git a/x b/x" "--- a/x" "$token"
  run_so diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 2 ]; check $? "6 a packet naming $token exits 2"
  [ ! -s "$OUT" ]; check $? "6 a packet naming $token prints nothing on stdout"
  [ ! -e "$WORK/ran" ]; check $? "6 a packet naming $token never calls codex"
  [ ! -e "$OPINION" ]; check $? "6 a packet naming $token leaves no --out"
  [ "$(lines "$ERR")" = 1 ]; check $? "6 a packet naming $token prints one line on stderr"
  grep -qE '(^|[^0-9])3([^0-9]|$)' "$ERR"; check $? "6 a packet naming $token names the offending line number"
done

fake_codex 0 "P3 a nit" ""
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/.env.example" "+ SECRET_NAME=" \
  "process.env.SECRET_NAME" "config.foo.environment = 'test'" "valid_rsa_signature(sig)" \
  "invalid_rsa" "import x from 'node.ssh/client'"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ]; check $? "7 a packet naming only .env.example, process.env, an environment field, an rsa word inside an identifier or an import path ending .ssh/ exits 0"
[ -e "$WORK/ran" ]; check $? "7 a packet naming only benign secret-like words calls codex"
[ -s "$OPINION" ]; check $? "7 a packet naming only benign secret-like words fills --out"
[ ! -s "$ERR" ]; check $? "7 a packet naming only benign secret-like words prints nothing on stderr"

write_packet "goal: ship it" "constraint: one attempt" "assumption: the cache is warm"
fake_codex 0 "REFUTE the cache is cold on boot" ""
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ]; check $? "8 diff on a plan packet exits 0"
diff_preamble="$(preamble)"
check $? "8 diff prepends a contract paragraph before the packet"
run_so plan --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ]; check $? "8 plan exits 0"
plan_preamble="$(preamble)"
check $? "8 plan prepends a contract paragraph before the packet"
[ -n "$(printf '%s' "$plan_preamble" | tr -d '[:space:]')" ]; check $? "8 the plan contract paragraph is not blank"
[ "$diff_preamble" != "$plan_preamble" ]; check $? "8 plan prepends its own contract paragraph, not the diff one"

usage_exit "no mode"
usage_exit "an unknown mode" review --packet "$PACKET" --out "$OPINION"
usage_exit "flags without a mode" --packet "$PACKET" --out "$OPINION"
usage_exit "a missing --out flag" diff --packet "$PACKET"
usage_exit "a missing --packet flag" diff --out "$OPINION"
usage_exit "a missing --packet value" diff --packet --out "$OPINION"
usage_exit "an unknown flag" diff --packet "$PACKET" --out "$OPINION" --verbose
usage_exit "an absent packet" diff --packet "$WORK/absent" --out "$OPINION"

mkdir -p "$WORK/readonly"
chmod 500 "$WORK/readonly"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
cannot_write_exit "a read-only directory" "$WORK/readonly/opinion"
[ ! -e "$WORK/readonly/opinion" ]; check $? "10 an --out in a read-only directory creates nothing"
chmod 700 "$WORK/readonly"
cannot_write_exit "an absent directory" "$WORK/absent-dir/opinion"
[ ! -e "$WORK/absent-dir" ]; check $? "10 an --out in an absent directory creates nothing"

for line in "exec: grep -n login src/auth.ts" "exec: sed -n 12p src/quota.ts" \
  "rate limit: 60 requests per minute in the header" "exec: grep -n 'usage limit' docs/api.md"; do
  available_run "P2 x.ts:3 the mechanism" "$line"
done
available_run "P2 x.ts:3 the mechanism" "You've hit your usage limit."
available_run "P2 y.ts:1 finding" "Run codex login or provide an API key"

fake_codex 3 "partial finding" '
second line reason'
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ]; check $? "12 a blank first stderr line exits 1"
[ ! -s "$OUT" ]; check $? "12 a blank first stderr line prints nothing on stdout"
[ "$(cat "$ERR")" = "second-opinion unavailable: second line reason" ]; check $? "12 a blank first stderr line is skipped for the reason"
[ ! -e "$OPINION" ]; check $? "12 the partial --out is removed"
[ -s "$OPINION.stderr" ]; check $? "12 a blank first stderr line keeps the transcript"

fake_codex 0 "" ""
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ]; check $? "13 codex silent on both streams exits 1"
[ ! -s "$OUT" ]; check $? "13 codex silent on both streams prints nothing on stdout"
[ "$(cat "$ERR")" = "second-opinion unavailable: no output from codex" ]; check $? "13 codex silent on both streams is unavailable with no output from codex"
[ ! -e "$OPINION" ]; check $? "13 codex silent on both streams leaves no --out"
[ -e "$OPINION.stderr" ]; check $? "13 codex silent on both streams keeps the transcript"

fake_codex 0 "P1 a finding" ""
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
rm -f "$WORK/ran"
PATH="$WORK/bin:$PATH" TMPDIR=/nonexistent/dir /bin/bash "$SCRIPT" diff --packet "$PACKET" \
  --out "$OPINION" >"$OUT" 2>"$ERR"
status=$?
[ "$status" = 2 ]; check $? "14 a temp file that cannot be created exits 2"
[ ! -s "$OUT" ]; check $? "14 a temp file that cannot be created prints nothing on stdout"
[ ! -e "$WORK/ran" ]; check $? "14 a temp file that cannot be created never calls codex"
[ ! -e "$OPINION" ]; check $? "14 a temp file that cannot be created leaves no --out"
grep -q '^second-opinion: cannot create a temp file$' "$ERR"; check $? "14 a temp file that cannot be created says so"

summary
