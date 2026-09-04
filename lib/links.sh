conflict() {
  echo "CONFLICT: $1 ($2)" >&2
  conflicts=1
}

normalize() {
  local rest="$1/" part out=''
  while [ -n "$rest" ]; do
    part="${rest%%/*}"; rest="${rest#*/}"
    case "$part" in ''|.) ;; ..) out="${out%/*}" ;; *) out="$out/$part" ;; esac
  done
  echo "${out:-/}"
}

resolved_link_target() {
  local target
  target="$(readlink "$1")"
  case "$target" in /*) ;; *) target="$(cd "$(dirname "$1")" && pwd -P)/$target" ;; esac
  normalize "$target"
}

relink() {
  echo "  $1: $3 -> $2"
  pending=1
  [ "$CHECK" = 1 ] && return 0
  mkdir -p "$(dirname "$3")"
  # ln -sfn on a real directory would create the link inside it; the tree is byte-identical.
  [ -d "$3" ] && [ ! -L "$3" ] && rm -r "$3"
  ln -sfn "$2" "$3"
}

link_target() {
  local source="$1" target="$2" current
  if [ -L "$target" ]; then
    current="$(resolved_link_target "$target")"
    if [ "$current" = "$source" ]; then echo "  ok: $target -> $source"; return 0; fi
    case "$current" in
      "$REPO"/*) relink link "$source" "$target" ;;
      *) conflict "$target" "foreign symlink -> $current" ;;
    esac
  elif [ -f "$target" ] && [ -f "$source" ]; then
    if cmp -s "$source" "$target"; then relink adopt "$source" "$target"
    else conflict "$target" "content differs from $source"; fi
  elif [ -d "$target" ] && [ -d "$source" ]; then
    if diff -r -q "$source" "$target" >/dev/null 2>&1; then relink adopt "$source" "$target"
    else conflict "$target" "content differs from $source"; fi
  elif [ -e "$target" ]; then
    conflict "$target" "foreign path"
  else
    relink link "$source" "$target"
  fi
}

prune() {
  local path source
  for path in "$@"; do
    [ -L "$path" ] || continue
    source="$(resolved_link_target "$path")"
    case "$source" in "$REPO"/*) ;; *) continue ;; esac
    [ -e "$source" ] && continue
    echo "  prune: $path -> $source"
    pending=1
    [ "$CHECK" = 1 ] || rm "$path"
  done
}

report_foreign() {
  local source_dir="$1" path
  shift
  for path in "$@"; do
    { [ -e "$path" ] || [ -L "$path" ]; } || continue
    [ -L "$path" ] && [ "$(resolved_link_target "$path")" = "$source_dir/$(basename "$path")" ] && continue
    echo "  foreign: $path"
    pending=1
  done
}
