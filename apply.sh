#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd -P)"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CHECK=0
case "${1:-}" in
  --check) CHECK=1 ;;
  '') ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

conflicts=0
pending=0

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

link_target "$REPO/claude/CLAUDE.md" "$CLAUDE_HOME/CLAUDE.md"
for source in "$REPO"/claude/skills/*; do
  [ -d "$source" ] && link_target "$source" "$CLAUDE_HOME/skills/$(basename "$source")"
done
for source in "$REPO"/claude/agents/*.md; do
  [ -f "$source" ] && link_target "$source" "$CLAUDE_HOME/agents/$(basename "$source")"
done
for source in "$REPO"/claude/rules/*.md; do
  [ -f "$source" ] && link_target "$source" "$CLAUDE_HOME/rules/$(basename "$source")"
done
for source in "$REPO"/claude/hooks/*; do
  [ -f "$source" ] && link_target "$source" "$CLAUDE_HOME/hooks/$(basename "$source")"
done

prune "$CLAUDE_HOME/CLAUDE.md" "$CLAUDE_HOME"/skills/* "$CLAUDE_HOME"/agents/* \
  "$CLAUDE_HOME"/rules/* "$CLAUDE_HOME"/hooks/*
report_foreign "$REPO/claude/skills" "$CLAUDE_HOME"/skills/*
report_foreign "$REPO/claude/agents" "$CLAUDE_HOME"/agents/*
report_foreign "$REPO/claude/rules" "$CLAUDE_HOME"/rules/*
report_foreign "$REPO/claude/hooks" "$CLAUDE_HOME"/hooks/*

settings_status=0
if [ "$CHECK" = 1 ]; then
  python3 "$REPO/scripts/merge_settings.py" --settings "$CLAUDE_HOME/settings.json" \
    --hooks-dir "$CLAUDE_HOME/hooks" --manifest "$REPO/claude/hooks.json" --check \
    || settings_status=$?
  if [ "$pending" = 0 ] && [ "$conflicts" = 0 ] && [ "$settings_status" = 0 ]; then exit 0; fi
  exit 1
fi

python3 "$REPO/scripts/merge_settings.py" --settings "$CLAUDE_HOME/settings.json" \
  --hooks-dir "$CLAUDE_HOME/hooks" --manifest "$REPO/claude/hooks.json" || settings_status=$?
if [ "$conflicts" = 0 ] && [ "$settings_status" = 0 ]; then
  echo "Applied. Restart Claude Code sessions to pick up changes."
  exit 0
fi
exit 1
