#!/bin/bash
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd -P)"
CHECK=0
if [ "${1:-}" = --check ]; then CHECK=1; shift; fi
if [ "$#" != 1 ] || [ ! -d "$1" ]; then echo "usage: $0 [--check] <folder>" >&2; exit 2; fi
FOLDER="$(cd "$1" && pwd -P)"
RULES_DIR="$FOLDER/.claude/rules"
RULESET="$REPO/claude/rulesets/typescript"

conflicts=0
pending=0
. "$REPO/lib/links.sh"

for dir in "$FOLDER/.claude" "$RULES_DIR"; do
  if [ -L "$dir" ]; then echo "CONFLICT: $dir (symlink; links would land outside $FOLDER)" >&2; exit 1; fi
done
[ "$CHECK" = 1 ] || mkdir -p "$RULES_DIR"
for source in "$RULESET"/*.md; do
  [ -f "$source" ] && link_target "$source" "$RULES_DIR/$(basename "$source")"
done
prune "$RULES_DIR"/*
report_foreign "$RULESET" "$RULES_DIR"/*

if [ "$CHECK" = 1 ]; then
  if [ "$pending" = 0 ] && [ "$conflicts" = 0 ]; then exit 0; fi
  exit 1
fi
[ "$conflicts" = 0 ] || exit 1
echo "Applied to $FOLDER."
