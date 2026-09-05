#!/bin/bash
set -u

HERE="$(cd "$(dirname "$0")" && pwd -P)"
SCRIPT="$HERE/../bin/second-opinion-codex"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ai-config-so-test.XXXXXX")" || exit 1
trap 'chmod -R u+rwx "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT
WORK="$(cd "$WORK" && pwd -P)" || exit 1

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

pass=0
fail=0
check() {
  if [ "$1" = 0 ]; then echo "PASS $2"; pass=$((pass + 1)); else echo "FAIL $2"; fail=$((fail + 1)); fi
}

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

lines() { wc -l < "$1" | tr -d ' '; }

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
  run_so "$@"
  [ "$status" = 2 ] && [ ! -s "$OUT" ] && grep -q '^usage: ' "$ERR" && [ ! -e "$WORK/ran" ]
}

cannot_write_exit() {
  run_so diff --packet "$PACKET" --out "$1"
  [ "$status" = 2 ] && [ ! -s "$OUT" ] && [ ! -e "$WORK/ran" ] \
    && [ "$(cat "$ERR")" = "second-opinion: cannot write $1" ]
}

available_run() {
  fake_codex 0 "$1" "$2"
  run_so diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 0 ] && [ ! -s "$OUT" ] && [ ! -s "$ERR" ] \
    && [ "$(cat "$OPINION")" = "$1" ] && [ "$(cat "$OPINION.stderr")" = "$2" ]
}

fake_codex 0 "P1 lib/links.sh:12 the mechanism" "sandbox: read-only"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ] && [ ! -s "$OUT" ] && [ ! -s "$ERR" ] \
  && [ "$(cat "$OPINION")" = "P1 lib/links.sh:12 the mechanism" ] \
  && [ "$(cat "$OPINION.stderr")" = "sandbox: read-only" ] \
  && [ "$(cat "$WORK/ca")" = /etc/ssl/cert.pem ] \
  && grep -q -F -- 'exec -s read-only --ignore-user-config -' "$WORK/argv" \
  && [ -n "$(preamble | tr -d '[:space:]')" ] \
  && tail -n "$(lines "$PACKET")" "$WORK/stdin" | cmp -s - "$PACKET"
check $? "1 diff calls codex read-only with the certificate set, the contract paragraph before the packet and the packet verbatim, exits 0 and fills --out and --out.stderr"

fake_codex 7 "" 'stream error: unexpected status 500
retrying in 1s'
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ] && [ ! -s "$OUT" ] \
  && [ "$(cat "$ERR")" = "second-opinion unavailable: stream error: unexpected status 500" ] \
  && [ "$(lines "$WORK/calls")" = 1 ] && [ ! -e "$OPINION" ] && [ -s "$OPINION.stderr" ]
check $? "2 a non-zero codex exit is unavailable with the first stderr line, exits 1, prints nothing on stdout, keeps the transcript, leaves no --out and calls codex exactly once"

fake_codex 0 "" "model returned no message"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ] && [ ! -s "$OUT" ] \
  && [ "$(cat "$ERR")" = "second-opinion unavailable: model returned no message" ] \
  && [ ! -e "$OPINION" ]
check $? "3 empty codex stdout is unavailable, exits 1 and leaves no --out although codex exited 0"

reason_line=0
for phrase in "You've hit your usage limit." "Not logged in" "Login is required to continue" \
  "quota exceeded" "rate limit exceeded"; do
  fake_codex 0 "" "sandbox: read-only
$phrase"
  run_so diff --packet "$PACKET" --out "$OPINION"
  { [ "$status" = 1 ] && [ "$(cat "$ERR")" = "second-opinion unavailable: $phrase" ] \
    && [ "$(lines "$WORK/calls")" = 1 ] && [ ! -e "$OPINION" ]; } || reason_line=1
done
[ "$reason_line" = 0 ]
check $? "4 the reason names codex's own usage limit, quota, rate limit or missing login wherever that line sits in the transcript, not the first line"

fake_codex 0 "P1 a finding" ""
rm -f "$WORK/ran"
PATH=/usr/bin:/bin /bin/bash "$SCRIPT" diff --packet "$PACKET" --out "$OPINION" >"$OUT" 2>"$ERR"
status=$?
[ "$status" = 1 ] && [ ! -s "$OUT" ] && [ "$(lines "$ERR")" = 1 ] \
  && grep -q '^second-opinion unavailable: ' "$ERR" && [ ! -e "$WORK/ran" ] \
  && [ ! -e "$OPINION" ]
check $? "5 codex absent from PATH is unavailable, exits 1 and leaves no --out"

secrets=0
for token in "+++ b/.env" "+++ b/.env.local" "-----BEGIN OPENSSH PRIVATE KEY" "cp id_rsa /tmp/k" \
  "cp my_id_rsa /tmp/k" "id_ed25519.pub" "cat ~/.ssh/config" "/Users/x/.ssh/known_hosts" \
  "cat .ssh/config"; do
  write_packet "diff --git a/x b/x" "--- a/x" "$token"
  run_so diff --packet "$PACKET" --out "$OPINION"
  { [ "$status" = 2 ] && [ ! -s "$OUT" ] && [ ! -e "$WORK/ran" ] && [ ! -e "$OPINION" ] \
    && [ "$(lines "$ERR")" = 1 ] && grep -qE '(^|[^0-9])3([^0-9]|$)' "$ERR"; } || secrets=1
done
[ "$secrets" = 0 ]
check $? "6 a packet naming a dotenv file, a private-key marker, a private-key file name behind an underscore or an ssh directory is refused with the offending line number, exits 2 and never calls codex"

fake_codex 0 "P3 a nit" ""
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/.env.example" "+ SECRET_NAME=" \
  "process.env.SECRET_NAME" "config.foo.environment = 'test'" "valid_rsa_signature(sig)" \
  "invalid_rsa" "import x from 'node.ssh/client'"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ] && [ -e "$WORK/ran" ] && [ -s "$OPINION" ] && [ ! -s "$ERR" ]
check $? "7 a packet naming only .env.example, process.env, an environment field, an rsa word inside an identifier or an import path ending .ssh/ is not refused"

write_packet "goal: ship it" "constraint: one attempt" "assumption: the cache is warm"
fake_codex 0 "REFUTE the cache is cold on boot" ""
run_so diff --packet "$PACKET" --out "$OPINION"
diff_status=$status
diff_preamble="$(preamble)"
diff_read=$?
run_so plan --packet "$PACKET" --out "$OPINION"
plan_preamble="$(preamble)"
plan_read=$?
[ "$diff_status" = 0 ] && [ "$status" = 0 ] && [ "$diff_read" = 0 ] && [ "$plan_read" = 0 ] \
  && [ -n "$(printf '%s' "$plan_preamble" | tr -d '[:space:]')" ] \
  && [ "$diff_preamble" != "$plan_preamble" ]
check $? "8 plan prepends its own contract paragraph, not the diff one"

usage_errors=0
usage_exit || usage_errors=1
usage_exit review --packet "$PACKET" --out "$OPINION" || usage_errors=1
usage_exit --packet "$PACKET" --out "$OPINION" || usage_errors=1
usage_exit diff --packet "$PACKET" || usage_errors=1
usage_exit diff --out "$OPINION" || usage_errors=1
usage_exit diff --packet --out "$OPINION" || usage_errors=1
usage_exit diff --packet "$PACKET" --out "$OPINION" --verbose || usage_errors=1
usage_exit diff --packet "$WORK/absent" --out "$OPINION" || usage_errors=1
[ "$usage_errors" = 0 ]
check $? "9 no mode, an unknown mode, a missing flag, a missing value, an unknown flag or an absent packet exits 2 with a usage line and never calls codex"

mkdir -p "$WORK/readonly"
chmod 500 "$WORK/readonly"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
cannot_write_exit "$WORK/readonly/opinion"
readonly_dir=$?
[ ! -e "$WORK/readonly/opinion" ]
readonly_clean=$?
chmod 700 "$WORK/readonly"
cannot_write_exit "$WORK/absent-dir/opinion"
absent_dir=$?
[ "$readonly_dir" = 0 ] && [ "$readonly_clean" = 0 ] && [ "$absent_dir" = 0 ] \
  && [ ! -e "$WORK/absent-dir" ]
check $? "10 an --out in a read-only or absent directory exits 2 naming the file it cannot write, creates nothing and never calls codex"

benign=0
for line in "exec: grep -n login src/auth.ts" "exec: sed -n 12p src/quota.ts" \
  "rate limit: 60 requests per minute in the header" "exec: grep -n 'usage limit' docs/api.md"; do
  available_run "P2 x.ts:3 the mechanism" "$line" || benign=1
done
available_run "P2 x.ts:3 the mechanism" "You've hit your usage limit." || benign=1
available_run "P2 y.ts:1 finding" "Run codex login or provide an API key" || benign=1
[ "$benign" = 0 ]
check $? "11 codex exiting 0 with findings is available whatever its stderr says, a usage limit or a login phrase included: exits 0 with the codex stdout verbatim in --out"

fake_codex 3 "partial finding" '
second line reason'
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ] && [ ! -s "$OUT" ] \
  && [ "$(cat "$ERR")" = "second-opinion unavailable: second line reason" ] \
  && [ ! -e "$OPINION" ] && [ -s "$OPINION.stderr" ]
check $? "12 a blank first stderr line is skipped for the reason and the partial --out is removed"

fake_codex 0 "" ""
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ] && [ ! -s "$OUT" ] \
  && [ "$(cat "$ERR")" = "second-opinion unavailable: no output from codex" ] \
  && [ ! -e "$OPINION" ] && [ -e "$OPINION.stderr" ]
check $? "13 codex silent on both streams is unavailable with no output from codex and leaves no --out"

fake_codex 0 "P1 a finding" ""
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
rm -f "$WORK/ran"
PATH="$WORK/bin:$PATH" TMPDIR=/nonexistent/dir /bin/bash "$SCRIPT" diff --packet "$PACKET" \
  --out "$OPINION" >"$OUT" 2>"$ERR"
status=$?
[ "$status" = 2 ] && [ ! -s "$OUT" ] && [ ! -e "$WORK/ran" ] && [ ! -e "$OPINION" ] \
  && grep -q '^second-opinion: cannot create a temp file$' "$ERR"
check $? "14 a temp file that cannot be created exits 2 saying so, leaves no --out and never calls codex"

echo "PASS $pass FAIL $fail"
[ "$fail" = 0 ]
