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

run_so_in() {
  local dir="$1"
  shift
  rm -f "$WORK/ran" "$WORK/calls" "$WORK/stdin" "$WORK/argv" "$WORK/ca" "$OPINION" "$OPINION.stderr"
  ( cd "$dir" && PATH="$WORK/bin:$PATH" exec /bin/bash "$SCRIPT" "$@" ) >"$OUT" 2>"$ERR"
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
[ "$(cat "$ERR")" = "second-opinion-codex unavailable: stream error: unexpected status 500" ]; check $? "2 a non-zero codex exit is unavailable with the first stderr line"
[ "$(lines "$WORK/calls")" = 1 ]; check $? "2 a non-zero codex exit calls codex exactly once"
[ ! -e "$OPINION" ]; check $? "2 a non-zero codex exit leaves no --out"
[ -s "$OPINION.stderr" ]; check $? "2 a non-zero codex exit keeps the transcript"

fake_codex 0 "" "model returned no message"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 1 ]; check $? "3 empty codex stdout exits 1 although codex exited 0"
[ ! -s "$OUT" ]; check $? "3 empty codex stdout prints nothing on stdout"
[ "$(cat "$ERR")" = "second-opinion-codex unavailable: model returned no message" ]; check $? "3 empty codex stdout is unavailable with the stderr line"
[ ! -e "$OPINION" ]; check $? "3 empty codex stdout leaves no --out"

fake_codex 0 "P1 a finding" ""
rm -f "$WORK/ran"
PATH=/usr/bin:/bin /bin/bash "$SCRIPT" diff --packet "$PACKET" --out "$OPINION" >"$OUT" 2>"$ERR"
status=$?
[ "$status" = 1 ]; check $? "4 codex absent from PATH exits 1"
[ ! -s "$OUT" ]; check $? "4 codex absent from PATH prints nothing on stdout"
[ "$(lines "$ERR")" = 1 ]; check $? "4 codex absent from PATH prints one line on stderr"
grep -q '^second-opinion-codex unavailable: ' "$ERR"; check $? "4 codex absent from PATH is unavailable"
[ ! -e "$WORK/ran" ]; check $? "4 codex absent from PATH never calls codex"
[ ! -e "$OPINION" ]; check $? "4 codex absent from PATH leaves no --out"

for item in $'+++ b/.env\ta credential path\t.env' $'+++ b/.env.local\ta credential path\t.env' \
  $'-----BEGIN OPENSSH PRIVATE KEY\ta credential path\t-----BEGIN' $'cp id_rsa /tmp/k\ta credential path\tid_rsa' \
  $'cp my_id_rsa /tmp/k\ta credential path\tid_rsa' $'id_ed25519.pub\ta credential path\tid_ed25519' \
  $'cat ~/.ssh/config\ta credential path\t.ssh/' $'/Users/x/.ssh/known_hosts\ta credential path\t.ssh/' \
  $'cat .ssh/config\ta credential path\t.ssh/' $'customer-data/export.json\tpersonal data\tcustomer-data' \
  $'gdpr/subjects.json\tpersonal data\tgdpr' $'+++ b/PII/subjects.json\tpersonal data\tPII'; do
  IFS=$'\t' read -r token class expected <<< "$item"
  write_packet "diff --git a/x b/x" "--- a/x" "$token"
  run_so diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 2 ]; check $? "5 a packet naming $token exits 2"
  [ ! -e "$WORK/ran" ]; check $? "5 a packet naming $token never calls codex"
  grep -q "^second-opinion-codex refused: packet line 3 names $class: " "$ERR"; check $? "5 a packet naming $token names its class, $class"
  grep -qF -- "$expected" "$ERR"; check $? "5 a packet naming $token names the matching path $expected"
done

fake_codex 0 "P3 a nit" ""
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/.env.example" "+ SECRET_NAME=" \
  "process.env.SECRET_NAME" "config.foo.environment = 'test'" "valid_rsa_signature(sig)" \
  "invalid_rsa" "import x from 'node.ssh/client'" "src/customers/repository.ts" "analytics/user_events.ts"
run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 0 ]; check $? "6 a packet naming only .env.example, process.env, an environment field, an rsa word inside an identifier, an import path ending .ssh/, a customers directory or a user_events file exits 0"
[ -e "$WORK/ran" ]; check $? "6 a packet naming only benign secret-like words calls codex"
[ -s "$OPINION" ]; check $? "6 a packet naming only benign secret-like words fills --out"
[ ! -s "$ERR" ]; check $? "6 a packet naming only benign secret-like words prints nothing on stderr"

scratch_repo() {
  mkdir -p "$WORK/$1/sub"
  git -C "$WORK/$1" init -q
  echo "$WORK/$1"
}

refused_in() {
  local dir="$1" label="$2" class="$3" match="$4"
  run_so_in "$dir" diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 2 ]; check $? "7 $label exits 2"
  [ ! -s "$OUT" ]; check $? "7 $label prints nothing on stdout"
  [ ! -e "$WORK/ran" ]; check $? "7 $label never calls codex"
  [ ! -e "$OPINION" ]; check $? "7 $label leaves no --out"
  [ "$(cat "$ERR")" = "second-opinion-codex refused: packet line 3 names $class: $match" ]; check $? "7 $label names the class and the matching path"
}

sent_in() {
  local dir="$1" label="$2"
  run_so_in "$dir" diff --packet "$PACKET" --out "$OPINION"
  [ "$status" = 0 ]; check $? "7 $label exits 0"
  [ -e "$WORK/ran" ]; check $? "7 $label calls codex"
  [ -s "$OPINION" ]; check $? "7 $label fills --out"
  [ ! -s "$ERR" ]; check $? "7 $label prints nothing on stderr"
}

fake_codex 0 "P1 a finding" ""
LISTED="$(scratch_repo listed)"
printf '%s\n' "docs/internal.md" > "$LISTED/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/internal.md"
refused_in "$LISTED" "a path listed in .confidential" "a path .confidential marks" "docs/internal.md"
refused_in "$LISTED/sub" "a path listed in .confidential, run from a subdirectory of the repository" "a path .confidential marks" "docs/internal.md"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/external.md"
sent_in "$LISTED" "a path .confidential does not list"

GLOB="$(scratch_repo glob)"
printf '%s\n' "secrets/*.yaml" > "$GLOB/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/secrets/prod.yaml"
refused_in "$GLOB" "a path matching a .confidential glob" "a path .confidential marks" "secrets/prod.yaml"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/secrets/README.md"
sent_in "$GLOB" "a path beside a .confidential glob that does not match it"

LITERAL="$(scratch_repo literal)"
printf '%s\n' "docs/(draft).md" > "$LITERAL/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/(draft).md"
refused_in "$LITERAL" "a .confidential entry carrying regex metacharacters" "a path .confidential marks" "docs/(draft).md"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/draft.md" "+++ b/docs/(draft)xmd"
sent_in "$LITERAL" "a path the .confidential entry would match only if its metacharacters were not literal"

COMMENTED="$(scratch_repo commented)"
printf '%s\n' "docs/a.md" "" "# internal/" "internal/plan.md" > "$COMMENTED/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/a.md"
refused_in "$COMMENTED" "an entry above a blank line and a comment in .confidential" "a path .confidential marks" "docs/a.md"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/internal/plan.md"
refused_in "$COMMENTED" "an entry below a blank line and a comment in .confidential" "a path .confidential marks" "internal/plan.md"
write_packet "diff --git a/x b/x" "--- a/x" "# internal/" "+ added line"
sent_in "$COMMENTED" "a packet matching only the blank line and the comment in .confidential"

SPACED="$(scratch_repo spaced)"
printf 'docs/one.md \ndocs/two.md\r\n \n\t\n' > "$SPACED/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/one.md"
refused_in "$SPACED" "a .confidential entry with a trailing space" "a path .confidential marks" "docs/one.md"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/two.md"
refused_in "$SPACED" "a .confidential entry ending in CRLF" "a path .confidential marks" "docs/two.md"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
sent_in "$SPACED" "a packet in a repository whose .confidential has whitespace-only lines"

DASHED="$(scratch_repo dashed)"
printf '%s\n' "-x.md" > "$DASHED/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/-x.md"
refused_in "$DASHED" "a .confidential entry opening with a dash" "a path .confidential marks" "-x.md"

UNMARKED="$(scratch_repo unmarked)"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
sent_in "$UNMARKED" "a repository without .confidential"
write_packet "diff --git a/x b/x" "--- a/x" "id_ed25519.pub"
refused_in "$UNMARKED" "a credential path in a repository without .confidential" "a credential path" "id_ed25519"

EMPTY="$(scratch_repo empty)"
: > "$EMPTY/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+ added line"
sent_in "$EMPTY" "a repository with an empty .confidential"

mkdir -p "$WORK/plain"
printf '%s\n' "docs/internal.md" > "$WORK/plain/.confidential"
write_packet "diff --git a/x b/x" "--- a/x" "+++ b/docs/internal.md"
refused_in "$WORK/plain" "a path listed in .confidential of a directory outside any repository" "a path .confidential marks" "docs/internal.md"

printf 'diff --git a/x b/x\n--- a/x\n+ caf\xE9\n+++ b/.env\n' > "$PACKET"
LC_ALL=en_US.UTF-8 run_so diff --packet "$PACKET" --out "$OPINION"
[ "$status" = 2 ]; check $? "8 a credential path below a line with an invalid byte exits 2"
[ ! -s "$OUT" ]; check $? "8 a credential path below a line with an invalid byte prints nothing on stdout"
[ ! -e "$WORK/ran" ]; check $? "8 a credential path below a line with an invalid byte never calls codex"
[ ! -e "$OPINION" ]; check $? "8 a credential path below a line with an invalid byte leaves no --out"
[ "$(lines "$ERR")" = 1 ]; check $? "8 a credential path below a line with an invalid byte prints one line on stderr"
grep -q "^second-opinion-codex refused: packet line 4 names a credential path: " "$ERR"; check $? "8 a credential path below a line with an invalid byte names its class and line"
grep -qF -- ".env" "$ERR"; check $? "8 a credential path below a line with an invalid byte names the matching path .env"

summary
