#!/usr/bin/env python3
"""PreToolUse hook (Edit|Write|MultiEdit|NotebookEdit): dotenv files, the .git store, git-ignored generated directories and lerna-owned versions are read-only."""

import json
import os
import subprocess
import sys

HOOK = "write-guard.py"
GENERATED_DIRECTORY_NAMES = {"node_modules", "dist", "coverage", "build"}
GENERATED_PERMITTED = "edit the source that generates it."


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


def git_store_rule(segments):
    ancestors = segments[:-1]
    if ".git" not in ancestors:
        return None
    rest = segments[ancestors.index(".git") + 1:]
    if rest == ["info", "exclude"] or (rest[0] == "hooks" and len(rest) > 1):
        return None
    return deny("the .git directory is git's own store and is read-only.", ".git/info/exclude and .git/hooks/* only.")


def repository_root(directory):
    while True:
        if os.path.exists(os.path.join(directory, ".git")):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def git_ignores(root, directory):
    """True or False from git check-ignore; None when git could not answer."""
    directory_pathspec = os.path.relpath(directory, root) + "/"
    try:
        completed = subprocess.run(["git", "-C", root, "check-ignore", "-q", "--", directory_pathspec], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode in (0, 1):
        return completed.returncode == 0
    return None


def generated_directory_rule(segments):
    for depth, name in enumerate(segments[:-1]):
        if name not in GENERATED_DIRECTORY_NAMES:
            continue
        directory = "/".join(segments[: depth + 1])
        root = repository_root(directory)
        if root is None:
            return deny(f"'{name}' is a generated directory by name and lies outside any repository.", GENERATED_PERMITTED)
        ignored = git_ignores(root, directory)
        if ignored is None:
            return deny(f"'{name}' is a generated directory by name and git could not be consulted.", GENERATED_PERMITTED)
        if ignored:
            return deny(f"'{name}' is a git-ignored generated directory and is read-only.", GENERATED_PERMITTED)
    return None


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
    denied = git_store_rule(segments) or generated_directory_rule(segments)
    if denied:
        return denied

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
