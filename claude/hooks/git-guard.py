#!/usr/bin/env python3
"""PreToolUse hook (Bash): denies destructive git forms and any rm of a path the tree cannot regenerate; the settings `attribution` key stops Claude adding a trailer, the commit-text scan here is the backstop."""

import json
import os
import re
import shlex
import subprocess
import sys

HOOK = "git-guard.py"
ATTRIBUTION_TRAILER_KEYS = ("co-authored-by:", "claude-session:")
ATTRIBUTION_PHRASE = "generated with [claude code]"
SAFE_RM_PREFIXES = ("$TMPDIR", "${TMPDIR}", "/tmp/claude", "/private/tmp/claude")
TMPDIR_VARIABLE = re.compile(r"^\$(\{TMPDIR\}|TMPDIR)(?=/|$)")
UNRESOLVABLE_TARGET = re.compile(r"^~|[*?\[]|\$(?!TMPDIR(?=/|$)|\{TMPDIR\}(?=/|$))|`")
UNRESOLVABLE_PATHSPEC = re.compile(r"\$(?!PWD(?=/|$)|\{PWD\})|`")
SEGMENT_SPLIT = re.compile(r"\|\||&&|;|\n|\||(?<!&)&(?!&)")
GIT_GLOBAL_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--attr-source"}
WRAPPER_OPTIONS_WITH_VALUE = {
    "sudo": {"-u", "-g"},
    "doas": {"-u", "-C"},
    "command": set(),
    "env": {"-u", "-C", "-P", "-S"},
    "time": set(),
    "nice": {"-n"},
    "nohup": set(),
    "exec": {"-a"},
    "caffeinate": {"-t", "-w"},
    "xargs": {"-n", "-I", "-P", "-a", "-L", "-s", "-E"},
}
TIMEOUT_OPTIONS_WITH_VALUE = {"-k", "-s", "--kill-after", "--signal"}
SHELL_KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "!"}
SHELLS = {"sh", "bash", "zsh", "dash"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")
TREE_WIDE_PATHSPECS = {".", ":", ":/", "*", "**", "..", "../..", "$PWD", "${PWD}"}
PATHSPEC_MAGIC = re.compile(r"^:\(([^)]*)\)")
NEGATIVE_PATHSPEC_PREFIXES = (":!", ":^")
STASH_READ_ONLY_SUBCOMMANDS = {"list", "show"}
COMMIT_SHORT_VALUE_LETTERS = "mFCct"
COMMIT_LONG_VALUE_OPTIONS = {"--message": "m", "--file": "F", "--reuse-message": "C", "--reedit-message": "c", "--template": "t"}
FIND_GLOBAL_FLAGS = {"-H", "-L", "-P", "-E", "-X", "-x", "-s", "-d"}
FIND_NAME_PRIMARIES = {"-name", "-iname", "-path", "-ipath"}
FIND_ACTIONS = {"-delete", "-exec", "-execdir"}
FIND_BRANCHING = {"-o", "-or", "!", "-not", "("}
GIT_TIMEOUT_SECONDS = 2
MAX_DEPTH = 3


def split_segments(command):
    """Splits on list/pipe operators and unquoted parentheses; unterminated quotes fall back to a plain split."""
    segments, current, quote, index = [], [], None, 0
    while index < len(command):
        char = command[index]
        if quote:
            if char == quote:
                quote = None
            elif char == "\\" and quote == '"' and index + 1 < len(command):
                current.append(char)
                index += 1
                char = command[index]
            current.append(char)
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char == "\\" and index + 1 < len(command):
            current.extend(command[index : index + 2])
            index += 1
        elif command.startswith("$(", index):
            end, depth = index + 2, 1
            while end < len(command) and depth:
                depth += {"(": 1, ")": -1}.get(command[end], 0)
                end += 1
            current.extend(command[index:end])
            index = end - 1
        elif char in ";\n()|&":
            segments.append("".join(current))
            current = []
            if command.startswith(("||", "&&", "|&"), index):
                index += 1
        else:
            current.append(char)
        index += 1
    segments.append("".join(current))
    if quote:
        segments = SEGMENT_SPLIT.split(command)
    return [segment.strip() for segment in segments if segment.strip()]


def tokenize(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def skip_options(tokens, with_value):
    while tokens and tokens[0].startswith("-"):
        if tokens[0] == "--":
            return tokens[1:]
        tokens = tokens[2:] if tokens[0] in with_value else tokens[1:]
    return tokens


def strip_wrappers(tokens):
    """Returns (wrappers, tokens): the wrapper programs removed from the front, then the command they run."""
    wrappers = []
    while tokens:
        head = tokens[0]
        name = os.path.basename(head)
        if name in WRAPPER_OPTIONS_WITH_VALUE:
            wrappers.append(name)
            tokens = skip_options(tokens[1:], WRAPPER_OPTIONS_WITH_VALUE[name])
        elif head in SHELL_KEYWORDS or ENV_ASSIGNMENT.match(head):
            tokens = tokens[1:]
        elif name == "timeout":
            wrappers.append(name)
            tokens = skip_options(tokens[1:], TIMEOUT_OPTIONS_WITH_VALUE)
            if tokens and DURATION.match(tokens[0]):
                tokens = tokens[1:]
        elif head.startswith(("\\", "{")):
            tokens = ([head[1:]] if head[1:] else []) + tokens[1:]
        else:
            break
    if tokens and tokens[-1] == "}":
        tokens = tokens[:-1]
    return wrappers, tokens


def program(tokens):
    return os.path.basename(tokens[0]) if tokens else ""


def command_substitutions(text):
    """Yields the bodies of $(…) and `…` in text."""
    index = 0
    while index < len(text):
        if text.startswith("$(", index):
            depth, start = 1, index + 2
            end = start
            while end < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[end], 0)
                end += 1
            yield text[start : end - 1] if depth == 0 else text[start:]
            index = end
        elif text[index] == "`":
            end = text.find("`", index + 1)
            if end == -1:
                yield text[index + 1 :]
                return
            yield text[index + 1 : end]
            index = end + 1
        else:
            index += 1


def nested_commands(tokens):
    """Yields command strings a shell would evaluate from within this segment."""
    if program(tokens) in SHELLS:
        for index, token in enumerate(tokens[1:-1], start=1):
            if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
                yield tokens[index + 1]
                break
    elif program(tokens) == "eval":
        yield " ".join(tokens[1:])


def segments(command, depth=0):
    """Yields (wrappers, tokens) for every segment, including shell indirection."""
    if depth > MAX_DEPTH:
        return
    for segment in split_segments(command):
        wrappers, tokens = strip_wrappers(tokenize(segment))
        yield wrappers, tokens
        for nested in nested_commands(tokens):
            yield from segments(nested, depth + 1)
    for body in command_substitutions(command):
        yield from segments(body, depth + 1)


def git_invocation(tokens):
    """Returns (subcommand, args, global_options) when the segment invokes git, else None."""
    if program(tokens) != "git":
        return None
    rest = tokens[1:]
    position = 0
    while position < len(rest) and rest[position].startswith("-"):
        if rest[position] in GIT_GLOBAL_OPTIONS_WITH_VALUE:
            position += 2
        else:
            position += 1
    if position >= len(rest):
        return None
    return rest[position], rest[position + 1 :], rest[:position]


def short_flag_has(token, letters, value_letters=""):
    """True when a short-flag cluster carries one of letters before any letter that takes the rest as its value."""
    if not token.startswith("-") or token.startswith("--"):
        return False
    for letter in token[1:]:
        if letter in letters:
            return True
        if letter in value_letters:
            return False
    return False


def deny(rule, permitted):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{HOOK}: {rule} Permitted: {permitted}",
        }
    }


def defines_alias(global_options):
    for index, option in enumerate(global_options):
        if option == "-c" and index + 1 < len(global_options) and global_options[index + 1].lower().startswith("alias."):
            return True
        if option.startswith("-c") and option[2:].lower().startswith("alias."):
            return True
    return False


def repo_root(cwd):
    path = cwd
    while path:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return None


def pathspecs(args):
    return args[args.index("--") + 1 :] if "--" in args else []


def negative_pathspec(spec):
    if spec.startswith(NEGATIVE_PATHSPEC_PREFIXES):
        return True
    magic = PATHSPEC_MAGIC.match(spec)
    return magic is not None and "exclude" in magic.group(1).split(",")


def tree_wide_pathspec(args, cwd):
    specs = pathspecs(args)
    if not specs:
        return False
    if all(negative_pathspec(spec) for spec in specs):
        return True
    roots = {os.path.normpath(root) for root in (cwd, repo_root(cwd)) if root}
    for spec in specs:
        spec = os.path.normpath(PATHSPEC_MAGIC.sub("", spec))
        if spec in TREE_WIDE_PATHSPECS or spec.startswith(":/") or (os.path.isabs(spec) and spec in roots):
            return True
    return False


def unresolvable_pathspec(args):
    return any(UNRESOLVABLE_PATHSPEC.search(spec) for spec in pathspecs(args))


def stash_reads_only(args):
    return bool(args) and args[0] in STASH_READ_ONLY_SUBCOMMANDS


def commit_option_value(args, index):
    """Returns (flag, letter, value, consumed) when args[index] is a value-taking commit option, else None."""
    arg = args[index]
    following = args[index + 1] if index + 1 < len(args) else ""
    if arg.startswith("--"):
        name, has_value, value = arg.partition("=")
        letter = COMMIT_LONG_VALUE_OPTIONS.get(name)
        if letter is None:
            return None
        return (name, letter, value, 0) if has_value else (name, letter, following, 1)
    if arg.startswith("-"):
        for position, letter in enumerate(arg[1:], start=1):
            if letter in COMMIT_SHORT_VALUE_LETTERS:
                value = arg[position + 1 :]
                return (f"-{letter}", letter, value, 0) if value else (f"-{letter}", letter, following, 1)
    return None


def commit_options(args):
    """Yields (flag, letter, value) for each value-taking commit option before the pathspec separator."""
    index = 0
    while index < len(args) and args[index] != "--":
        option = commit_option_value(args, index)
        index += 1
        if option is None:
            continue
        flag, letter, value, consumed = option
        index += consumed
        yield flag, letter, value


def message_source(args):
    """Returns the flag whose message text the guard cannot read: a file, another commit, a template, or a shell-expanded -m."""
    for flag, letter, value in commit_options(args):
        if letter == "m":
            if "$" in value or "`" in value:
                return flag
        elif letter == "F":
            if value != "-":
                return flag
        else:
            return flag
    return None


def message_from_bare_stdin(args, tokens):
    reads_stdin = any(letter == "F" and value == "-" for _, letter, value in commit_options(args))
    return reads_stdin and not any(token.startswith("<<") for token in tokens)


def check_git(subcommand, args, global_options, cwd):
    if defines_alias(global_options):
        return deny("git -c alias.* defines a command the guard cannot see.", "the plain git subcommand.")
    if subcommand == "stash" and not stash_reads_only(args):
        return deny(
            "git stash silently destroys uncommitted work in a shared tree.",
            "to set a file aside, copy it and copy it back.",
        )
    if subcommand == "reset" and any(flag in args for flag in ("--hard", "--merge")):
        return deny(
            "git reset --hard/--merge discards everyone's uncommitted work in the tree.",
            "git reset (mixed/soft) or a copy-aside of the files you own.",
        )
    if subcommand == "clean":
        return deny("git clean deletes untracked work in a shared tree.", "delete the specific files you own by path.")
    if subcommand in ("checkout", "restore") and tree_wide_pathspec(args, cwd):
        return deny(
            f"tree-wide git {subcommand} pathspec reverts everyone's uncommitted work.",
            f"git {subcommand} … -- <pathspec you own>.",
        )
    if subcommand in ("checkout", "restore") and unresolvable_pathspec(args):
        return deny(
            f"git {subcommand} pathspec carries a shell substitution the guard cannot resolve.",
            f"name the path literally: git {subcommand} … -- <pathspec you own>.",
        )
    if subcommand == "checkout":
        if "-b" in args or "-B" in args or "--" in args:
            return None
        return deny(
            "tree-wide git checkout reverts everyone's uncommitted work.",
            "git checkout -b <branch>, or scope it: git checkout [<ref>] -- <pathspec you own>.",
        )
    if subcommand == "restore":
        if "--" in args:
            return None
        return deny(
            "tree-wide git restore reverts everyone's uncommitted work.",
            "git restore [--staged] -- <pathspec you own>.",
        )
    if subcommand == "switch":
        if "--discard-changes" in args or "--force" in args or any(short_flag_has(arg, "f", "cC") for arg in args):
            return deny(
                "git switch --discard-changes/-f throws away uncommitted work.",
                "git switch <branch> or git switch -c <branch>.",
            )
        return None
    if subcommand == "push":
        return deny("git push is the user's to run manually.", "leave the branch unpushed and say so in the report.")
    if subcommand == "commit":
        if "--all" in args or "--no-verify" in args or any(short_flag_has(arg, "an", COMMIT_SHORT_VALUE_LETTERS) for arg in args):
            return deny(
                "git commit -a/--all/--no-verify commits the whole tree or skips hooks.",
                "git commit -- <pathspec you own>; fix a failing hook, do not skip it.",
            )
        if "--amend" in args:
            return deny("git commit --amend rewrites an existing commit.", "make a new commit; squashing is the user's decision at review.")
        if not pathspecs(args):
            return deny("git commit without a pathspec commits the whole index.", "git commit … -- <paths>.")
    return None


def resolve_rm_target(target):
    tmpdir = os.environ.get("TMPDIR", "")
    if tmpdir:
        target = TMPDIR_VARIABLE.sub(tmpdir.rstrip("/"), target)
    return os.path.normpath(target)


def under_prefix(target, prefix):
    return target == prefix or target.startswith(prefix.rstrip("/") + "/")


def under_safe_prefix(target):
    tmpdir = os.environ.get("TMPDIR", "")
    prefixes = SAFE_RM_PREFIXES + ((tmpdir.rstrip("/"),) if tmpdir else ())
    return any(under_prefix(target, prefix) for prefix in prefixes) or (os.path.isabs(target) and "scratchpad" in target.split("/"))


def git_ignores(directory, path):
    try:
        code = subprocess.run(
            ["git", "-C", directory, "check-ignore", "-q", "--", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
        ).returncode
    except (OSError, subprocess.TimeoutExpired):
        return False
    return code == 0


def git_ignored_path(target, cwd):
    root = repo_root(cwd)
    if root is None:
        return False
    root = os.path.normpath(root)
    resolved = os.path.normpath(os.path.join(cwd, target))
    if resolved == root or not under_prefix(resolved, root) or os.path.islink(resolved):
        return False
    return git_ignores(root, os.path.relpath(resolved, root))


def deletable(target, cwd):
    resolved = resolve_rm_target(target)
    return under_safe_prefix(resolved) or git_ignored_path(resolved, cwd)


def unresolvable_delete(targets):
    return any(UNRESOLVABLE_TARGET.search(target) for target in targets)


def deletable_targets(targets, cwd):
    return all(deletable(target, cwd) for target in targets)


def deny_unresolvable_delete():
    return deny("delete target carries a shell substitution the guard cannot resolve.", "name the path literally.")


def deny_rm():
    return deny(
        "rm outside $TMPDIR, the scratchpad or a git-ignored path deletes work the tree cannot regenerate.",
        "mv <target> $TMPDIR/<name> — nothing is lost and the user can inspect it; a git-ignored path inside the repository may be deleted in place.",
    )


def rm_targets(args):
    if "--" in args:
        separator = args.index("--")
        return [arg for arg in args[:separator] if not arg.startswith("-")] + args[separator + 1 :]
    return [arg for arg in args if not arg.startswith("-")]


def check_rm(wrappers, tokens, cwd):
    if program(tokens) != "rm":
        return None
    targets = rm_targets(tokens[1:])
    if "xargs" in wrappers or unresolvable_delete(targets):
        return deny_unresolvable_delete()
    if deletable_targets(targets, cwd):
        return None
    return deny_rm()


def find_start_paths(args):
    paths = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "-f" and index + 1 < len(args):
            paths.append(args[index + 1])
            index += 2
        elif arg in FIND_GLOBAL_FLAGS:
            index += 1
        elif arg.startswith("-") or arg in ("(", "!"):
            break
        else:
            paths.append(arg)
            index += 1
    return paths or ["."]


def find_name_values(args):
    return [args[index + 1] for index, arg in enumerate(args[:-1]) if arg in FIND_NAME_PRIMARIES]


def find_wants_directories(args):
    if any(arg in FIND_BRANCHING for arg in args):
        return False
    types = [index for index, arg in enumerate(args[:-1]) if arg == "-type" and args[index + 1] == "d"]
    actions = [index for index, arg in enumerate(args) if arg in FIND_ACTIONS]
    return bool(types) and bool(actions) and types[0] < actions[0]


def ignored_name(cwd, name, directory):
    """A dir/ pattern matches an absent name only with the trailing slash."""
    return git_ignores(cwd, name) or (directory and not name.endswith("/") and git_ignores(cwd, name + "/"))


def ignored_names(args, cwd):
    names = find_name_values(args)
    directory = find_wants_directories(args)
    return bool(names) and repo_root(cwd) is not None and all(ignored_name(cwd, name, directory) for name in names)


def find_deletes(args):
    if "-delete" in args:
        return True
    for index, arg in enumerate(args):
        if arg in ("-exec", "-execdir"):
            action = args[index + 1 :]
            end = next((position for position, token in enumerate(action) if token in (";", "+")), len(action))
            if any(program(tokens) == "rm" for _, tokens in segments(shlex.join(action[:end]))):
                return True
    return False


def check_find(tokens, cwd):
    args = tokens[1:]
    if program(tokens) != "find" or not find_deletes(args):
        return None
    starts = find_start_paths(args)
    if unresolvable_delete(starts):
        return deny_unresolvable_delete()
    if deletable_targets(starts, cwd) or ignored_names(args, cwd):
        return None
    return deny_rm()


def commit_text_lines(command):
    """Yields each -m value's lines, then the command's own lines (a heredoc body)."""
    for _, tokens in segments(command):
        invocation = git_invocation(tokens)
        if invocation is not None and invocation[0] == "commit":
            for _, letter, value in commit_options(invocation[1]):
                if letter == "m":
                    yield from value.split("\n")
    yield from command.split("\n")


def is_attribution(line):
    lowered = line.lower()
    return any(key in lowered for key in ATTRIBUTION_TRAILER_KEYS) or ATTRIBUTION_PHRASE in lowered


def attribution_marker(command):
    """Returns the first attribution line of the commit text, else None."""
    for line in commit_text_lines(command):
        stripped = line.strip()
        if is_attribution(stripped):
            return stripped
    return None


def attribution_decision(command):
    marker = attribution_marker(command)
    if marker is None:
        return None
    return deny(
        f"commit text contains '{marker}'; commit messages carry no Claude attribution.",
        "the same message without the attribution line.",
    )


def evaluate(hook_input):
    if hook_input.get("tool_name") != "Bash":
        return None
    command = hook_input["tool_input"]["command"]
    if not isinstance(command, str):
        return None
    cwd = hook_input.get("cwd") or ""
    commits = False

    for wrappers, tokens in segments(command):
        invocation = git_invocation(tokens)
        if invocation is not None:
            subcommand, args, global_options = invocation
            decision = check_git(subcommand, args, global_options, cwd)
            if decision is not None:
                return decision
            if subcommand == "commit":
                commits = True
                if message_from_bare_stdin(args, tokens):
                    return attribution_decision(command) or deny(
                        "git commit -F - takes the message from a pipe or stdin the guard cannot read.",
                        "a heredoc in the command: git commit -F - -- <paths> <<'EOF' … EOF, or a literal -m.",
                    )
                source = message_source(args)
                if source is not None:
                    return deny(
                        f"git commit {source} takes the message from outside the command.",
                        "put the message in the command: -F - with a heredoc, or a literal -m.",
                    )
        decision = check_rm(wrappers, tokens, cwd) or check_find(tokens, cwd)
        if decision is not None:
            return decision

    return attribution_decision(command) if commits else None


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
