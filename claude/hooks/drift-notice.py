#!/usr/bin/env python3
"""SessionStart hook: a live tree that ./apply.sh --check reports as drifted from the repository is named in one line."""

import contextlib
import json
import os
import signal
import subprocess
import sys

CHECK_TIMEOUT = 5
DRIFT_PREFIXES = ("link:", "adopt:", "prune:", "foreign:", "generate:", "CONFLICT:", "settings: would change")
NOTICE = "ai-config drift: {drift}; run {apply_script}"


def config_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def repository():
    """Returns the repository two levels above the CLAUDE.md link, or None when the config dir holds no such file."""
    claude_md = os.path.realpath(os.path.join(config_home(), "CLAUDE.md"))
    if not os.path.isfile(claude_md):
        return None
    return os.path.dirname(os.path.dirname(claude_md))


def run_check(apply_script, repo):
    """Returns the exit status and merged output of apply.sh --check; a timeout kills its whole process group."""
    process = subprocess.Popen(
        ["/bin/bash", apply_script, "--check"],
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    return process.returncode, output


def first_drift(output):
    for line in output.splitlines():
        drift = line.strip()
        if drift.startswith(DRIFT_PREFIXES):
            return drift
    return None


def evaluate(hook_input):
    """Returns the drift line added to the session's context, or None when the live tree matches the repository."""
    if not isinstance(hook_input, dict):
        return None
    repo = repository()
    if repo is None:
        return None
    apply_script = os.path.join(repo, "apply.sh")
    if not os.path.isfile(apply_script):
        return None
    status, output = run_check(apply_script, repo)
    if status == 0:
        return None
    drift = first_drift(output)
    if drift is None:
        return None
    return NOTICE.format(drift=drift, apply_script=apply_script)


def main():
    try:
        notice = evaluate(json.loads(sys.stdin.read()))
        if notice is not None:
            print(notice)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
