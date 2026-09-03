#!/usr/bin/env python3
"""Merge the manifest's hook handlers into a Claude Code settings.json."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
from typing import Any

Manifest = dict[str, list[dict[str, Any]]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", required=True, type=Path)
    parser.add_argument("--hooks-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def hook_command(hooks_dir: Path, script: str) -> str:
    return " ".join(shlex.quote(argument) for argument in ("python3", str(hooks_dir / script)))


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def command_arguments(handler: Any) -> list[str]:
    if not isinstance(handler, dict):
        return []
    command = handler.get("command")
    if not isinstance(command, str):
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return []


def is_owned(handler: Any, owned_scripts: set[str]) -> bool:
    return any(os.path.basename(argument) in owned_scripts for argument in command_arguments(handler))


def without_owned(groups: list[Any], owned_scripts: set[str]) -> list[Any]:
    retained_groups: list[Any] = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            retained_groups.append(group)
            continue
        retained_handlers = [h for h in group["hooks"] if not is_owned(h, owned_scripts)]
        if retained_handlers:
            retained_groups.append({**group, "hooks": retained_handlers})
    return retained_groups


def owned_group(entry: dict[str, Any], hooks_dir: Path) -> dict[str, Any]:
    return {
        "matcher": entry["matcher"],
        "hooks": [
            {
                "type": "command",
                "command": hook_command(hooks_dir, entry["script"]),
                "timeout": entry["timeout"],
            }
        ],
    }


def merge(document: dict[str, Any], manifest: Manifest, hooks_dir: Path) -> dict[str, Any]:
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("settings field 'hooks' must be an object")
    owned_scripts = {entry["script"] for entries in manifest.values() for entry in entries}
    for script in owned_scripts:
        if "/" in script:
            raise ValueError(f"manifest script must be a bare file name: {script}")
    preexisting_empty = {event for event, groups in hooks.items() if groups == []}
    for event, groups in hooks.items():
        if isinstance(groups, list):
            hooks[event] = without_owned(groups, owned_scripts)
    for event, entries in manifest.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"settings field 'hooks.{event}' must be an array")
        groups.extend(owned_group(entry, hooks_dir) for entry in entries)
    for event in [e for e, groups in hooks.items() if groups == [] and e not in preexisting_empty]:
        del hooks[event]
    return document


def load_json_object(path: Path, missing: dict[str, Any] | None = None) -> dict[str, Any]:
    if missing is not None and not path.exists():
        return missing
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"unreadable JSON file: {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON file is not an object: {path}")
    return parsed


def current_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def write_atomic(path: Path, text: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(text)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> int:
    args = parse_args()
    try:
        manifest = load_json_object(args.manifest)
        document = load_json_object(args.settings, missing={})
        rendered = render(merge(document, manifest, args.hooks_dir))
    except (ValueError, KeyError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    unchanged = current_text(args.settings) == rendered
    if args.check:
        print("  settings: ok" if unchanged else "  settings: would change")
        return 0 if unchanged else 1
    if unchanged:
        print("  settings: unchanged")
        return 0
    try:
        write_atomic(args.settings, rendered)
    except OSError as error:
        print(f"ERROR: cannot write {args.settings}: {error}", file=sys.stderr)
        return 1
    print(f"  settings: updated {args.settings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
