HERE="$(cd "$(dirname "$0")" && pwd -P)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/${SCRATCH:?each suite names its scratch prefix}.XXXXXX")" || exit 1
WORK="$(cd "$WORK" && pwd -P)" || exit 1
# chmod first: rm -rf cannot empty a directory a suite left read-only.
trap 'chmod -R u+rwx "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

pass=0
fail=0
FAIL_DUMP=""

check() {
  if [ "$1" = 0 ]; then
    echo "PASS $2"
    pass=$((pass + 1))
  else
    echo "FAIL $2"
    if [ -n "$FAIL_DUMP" ] && [ -f "$FAIL_DUMP" ]; then cat "$FAIL_DUMP" >&2; fi
    fail=$((fail + 1))
  fi
}

links_to() { [ -L "$1" ] && [ "$(readlink "$1")" = "$2" ]; }

lines() { wc -l < "$1" | tr -d ' '; }

summary() {
  echo "PASS $pass FAIL $fail"
  [ "$fail" = 0 ]
}
