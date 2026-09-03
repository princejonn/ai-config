#!/usr/bin/env python3
"""PreToolUse hook (Edit|Write|MultiEdit|NotebookEdit): read-only paths and lerna-owned versions."""

import json
import os
import sys

HOOK = "write-guard.py"
READ_ONLY_SEGMENTS = {"node_modules", "dist", ".git", "coverage", "build"}


def deny(rule, permitted):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{HOOK}: {rule} Permitted: {permitted}",
        }
    }


def target_path(hook_input):
    tool_input = hook_input["tool_input"]
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    raw = raw.replace("\\", "/")
    if not os.path.isabs(raw):
        raw = os.path.join(hook_input.get("cwd") or "", raw)
    return os.path.realpath(raw)


def is_env_file(basename):
    return basename == ".env" or (basename.startswith(".env.") and basename != ".env.example")


def read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def version_differs(before_text, after_text):
    """True when both texts parse to JSON objects whose top-level "version" values differ."""
    try:
        before, after = json.loads(before_text), json.loads(after_text)
    except ValueError:
        return False
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    return before.get("version") != after.get("version")


def replaced_text(text, edits):
    """Applies each edit as the Edit tool would; None when an edit is malformed or its old_string is absent."""
    for edit in edits:
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or old not in text:
            return None
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def edit_changes_version(tool_input, path):
    on_disk = read_text(path)
    edits = tool_input.get("edits") or [tool_input]
    if on_disk is None or not isinstance(edits, list):
        return False
    edited = replaced_text(on_disk, edits)
    return edited is not None and version_differs(on_disk, edited)


def write_changes_version(tool_input, path):
    on_disk = read_text(path)
    content = tool_input.get("content")
    if on_disk is None or not isinstance(content, str):
        return False
    return version_differs(on_disk, content)


def evaluate(hook_input):
    path = target_path(hook_input)
    if path is None:
        return None
    basename = os.path.basename(path)
    segments = path.split("/")

    if is_env_file(basename):
        return deny("dotenv files hold secrets and are read-only.", "edit .env.example only.")
    blocked = READ_ONLY_SEGMENTS.intersection(segments[:-1])
    if blocked:
        return deny(f"'{sorted(blocked)[0]}' is a generated or vendored directory and is read-only.", "edit the source that generates it.")

    if basename != "package.json":
        return None
    tool_name = hook_input.get("tool_name")
    if tool_name == "Write":
        touches_version = write_changes_version(hook_input["tool_input"], path)
    else:
        touches_version = edit_changes_version(hook_input["tool_input"], path)
    if touches_version:
        return deny('the "version" field of package.json is owned by lerna.', "edit any other field; releases bump versions.")
    return None


def main():
    try:
        result = evaluate(json.loads(sys.stdin.read()))
        if result is not None:
            print(json.dumps(result))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
