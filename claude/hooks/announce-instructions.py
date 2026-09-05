#!/usr/bin/env python3
"""SessionStart hook: a repository whose root AGENTS.md the root CLAUDE.md does not import is announced by path and headings."""

import json
import os
import re
import sys

INSTRUCTIONS = "AGENTS.md"
IMPORTS = ("@AGENTS.md", "@./AGENTS.md")
HEADING = re.compile(r"^#{1,3} \S")
HEADING_LIMIT = 40
TRUNCATED = "…"
GATE = "Writes into this repository are gated on reading it in full."


def read_text(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def ancestors(directory):
    while True:
        yield directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return
        directory = parent


def repository_root(directory):
    for candidate in ancestors(directory):
        if os.path.exists(os.path.join(candidate, ".git")):
            return candidate
    for candidate in ancestors(directory):
        if os.path.isfile(os.path.join(candidate, INSTRUCTIONS)):
            return candidate
    return None


def headings(text):
    found = [line for line in text.splitlines() if HEADING.match(line)]
    if len(found) > HEADING_LIMIT:
        return found[:HEADING_LIMIT] + [TRUNCATED]
    return found


def imports_instructions(root):
    text = read_text(os.path.join(root, "CLAUDE.md"))
    return text is not None and any(line.strip() in IMPORTS for line in text.splitlines())


def evaluate(hook_input):
    """Returns the pointer added to the session's context, or None when nothing is announced."""
    if not isinstance(hook_input, dict):
        return None
    cwd = hook_input.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    directory = os.path.realpath(cwd)
    if not os.path.isdir(directory):
        return None
    root = repository_root(directory)
    if root is None:
        return None
    path = os.path.join(root, INSTRUCTIONS)
    text = read_text(path)
    if text is None or imports_instructions(root):
        return None
    return "\n".join([path, *headings(text), "", GATE])


def main():
    try:
        pointer = evaluate(json.loads(sys.stdin.read()))
        if pointer is not None:
            print(pointer)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
