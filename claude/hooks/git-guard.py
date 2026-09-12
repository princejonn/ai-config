#!/usr/bin/env python3
"""PreToolUse hook (Bash): denies destructive git forms, a push in any form but git push origin <branch>, any rm of a path the tree cannot regenerate, a commit subject that is not Conventional or a message with a bare §, and a test run piped through a pager; the settings `attribution` key stops Claude adding a trailer, the commit-text scan here is the backstop."""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import namedtuple

HOOK = "git-guard.py"
ATTRIBUTION_TRAILER_KEYS = ("co-authored-by:", "claude-session:")
ATTRIBUTION_PHRASE = "generated with [claude code]"
SAFE_RM_PREFIXES = ("$TMPDIR", "${TMPDIR}", "/tmp/claude", "/private/tmp/claude")
TMPDIR_VARIABLE = re.compile(r"^\$(\{TMPDIR\}|TMPDIR)(?=/|$)")
UNRESOLVABLE_TARGET = re.compile(r"^~|[*?\[]|\$(?!TMPDIR(?=/|$)|\{TMPDIR\}(?=/|$))|`")
UNRESOLVABLE_NAME = re.compile(r"^~|\$|`")
UNRESOLVABLE_PATHSPEC = re.compile(r"\$(?!PWD(?=/|$)|\{PWD\})|`")
UNRESOLVABLE_PROGRAM = re.compile(r"^[$`]")
SEGMENT_SPLIT = re.compile(r"(\|\||&&|\|&|;|\n|\||(?<![&<>])&(?![&>]))")
PIPE_OPERATORS = {"|", "|&"}
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
PUSH_COMMAND = re.compile(r"^git push origin (?!HEAD$|@$|(?:refs|heads|remotes|tags)/)\w[\w./-]*$")
COMMIT_SHORT_VALUE_LETTERS = "mFCct"
COMMIT_LONG_VALUE_OPTIONS = {"--message": "m", "--file": "F", "--reuse-message": "C", "--reedit-message": "c", "--template": "t"}
CONVENTIONAL_SUBJECT = re.compile(r"^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9][a-z0-9./,-]*\))?: \S")
CONVENTIONAL_TYPES = "build chore ci docs feat fix perf refactor revert style test"
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)(?:^\s*\2\s*$|\Z)", re.MULTILINE | re.DOTALL)
HEREDOC_DELIMITER = re.compile(r"^\w+$")
SPEC_BEFORE_SECTION = re.compile(r"(RFC\s?\d+|OIDC|Core|Discovery|OpenID)[^§]{0,20}$")
SECTION_LOOKBACK = 24
PACKAGE_MANAGERS = {"npm", "yarn", "pnpm"}
PACKAGE_MANAGER_OPTIONS_WITH_VALUE = {"--loglevel", "--prefix", "-w", "--workspace", "-C", "--userconfig", "--registry"}
NPX_OPTIONS_WITH_VALUE = {"-p", "--package"}
VERIFY_SCRIPT = re.compile(r"^(test.*|verify|typecheck.*|build|lint)$")
JS_RUNNERS = {"jest", "vitest", "mocha"}
PYTHON = re.compile(r"^python[0-9.]*$")
PYTHON_OPTIONS_WITH_VALUE = {"-W", "-X"}
PYTHON_TEST_MODULES = {"unittest", "pytest"}
MAKE_VERIFY_TARGETS = {"test", "check"}
PAGERS = {"tail", "head"}
FIND_GLOBAL_FLAGS = {"-H", "-L", "-P", "-E", "-X", "-x", "-s", "-d"}
FIND_FOLLOW_FLAGS = {"-H", "-L"}
FIND_MATCH = "{}"
FIND_EXEC_ACTIONS = {"-exec", "-execdir", "-ok", "-okdir"}
FIND_DIR_ACTIONS = {"-execdir", "-okdir"}
FIND_ACTIONS = FIND_EXEC_ACTIONS | {"-delete"}
FIND_UNPROMPTED_ACTIONS = {"-delete", "-exec", "-execdir"}
FIND_ACTION_TERMINATORS = {";", "+"}
FIND_NAME_PRIMARIES = {"-name", "-path"}
FIND_TYPES = {"d", "f"}
FIND_DEPTH_PRIMARIES = {"-maxdepth", "-mindepth"}
FIND_BARE_PRIMARIES = {"-prune", "-print", "-print0"}
GIT_TIMEOUT_SECONDS = 2
BUDGET_SECONDS = 8
MAX_DEPTH = 3
Span = namedtuple("Span", "kind start end closed")
WORD, ESCAPE, COMMENT, OPERATOR, REDIRECTION, HEREDOC_OPERATOR = "word", "escape", "comment", "operator", "redirection", "heredoc"
SINGLE, DOUBLE, ANSI, BACKTICK, SUBSTITUTION, EXPANSION, PROCESS = "single", "double", "ansi", "backtick", "substitution", "expansion", "process"
COMMAND, QUOTED_EXPANSION = "command", "quoted expansion"
QUOTES = {SINGLE, DOUBLE, ANSI}
TOKEN_BOUNDARIES = {OPERATOR, REDIRECTION, HEREDOC_OPERATOR}
BODY_OPENER = {SINGLE: 1, DOUBLE: 1, ANSI: 2, BACKTICK: 1, SUBSTITUTION: 2, EXPANSION: 2, PROCESS: 2}
COMMAND_OPERATORS = (
    ("<<<", REDIRECTION),
    ("<<-", HEREDOC_OPERATOR),
    ("<<", HEREDOC_OPERATOR),
    ("&>>", REDIRECTION),
    ("&>", REDIRECTION),
    (">&", REDIRECTION),
    ("<&", REDIRECTION),
    (">>", REDIRECTION),
    (">|", REDIRECTION),
    ("<>", REDIRECTION),
    (">", REDIRECTION),
    ("<", REDIRECTION),
    ("||", OPERATOR),
    ("&&", OPERATOR),
    ("|&", OPERATOR),
    ("|", OPERATOR),
    ("&", OPERATOR),
    (";", OPERATOR),
    ("\n", OPERATOR),
    ("(", OPERATOR),
    (")", OPERATOR),
)
CONSTRUCT_HEADS = set("'\"\\$`#") | {operator[0] for operator, _ in COMMAND_OPERATORS}
WHITESPACE = " \t\n"
WORD_HEAD = re.compile(r"[^ \t\n]*")
BACKTICK_ESCAPE = re.compile(r"\\([$`\\])")
ANSI_SIMPLE_ESCAPES = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
ANSI_OCTAL = re.compile(r"[0-7]{1,3}")
ANSI_HEX = re.compile(r"x([0-9A-Fa-f]{1,2})")


def flat_span(text, index, kind, closer, escapes):
    position = index + BODY_OPENER[kind]
    while position < len(text):
        if text[position] == closer:
            return Span(kind, index, position + 1, True)
        position += 2 if escapes and text[position] == "\\" else 1
    return Span(kind, index, len(text), False)


def nested_span(text, index, kind, context, closer):
    _, end = scan(text, index + BODY_OPENER[kind], context, closer)
    return Span(kind, index, len(text) if end is None else end, end is not None)


def expansion_context(context):
    return EXPANSION if context in (COMMAND, EXPANSION) else QUOTED_EXPANSION


def construct(text, index, context, at_token_start):
    """Returns the quote, escape, substitution, expansion, comment or operator span starting at index in this context, else None."""
    char = text[index]
    if context in (COMMAND, EXPANSION):
        if char == "'":
            return flat_span(text, index, SINGLE, "'", False)
        if text.startswith("$'", index):
            return flat_span(text, index, ANSI, "'", True)
        if text.startswith(("<(", ">("), index):
            return nested_span(text, index, PROCESS, COMMAND, ")")
    if char == '"' and context != DOUBLE:
        return nested_span(text, index, DOUBLE, DOUBLE, '"')
    if char == "\\" and index + 1 < len(text):
        return Span(ESCAPE, index, index + 2, True)
    if text.startswith("$(", index):
        return nested_span(text, index, SUBSTITUTION, COMMAND, ")")
    if text.startswith("${", index):
        return nested_span(text, index, EXPANSION, expansion_context(context), "}")
    if char == "`":
        return flat_span(text, index, BACKTICK, "`", True)
    if context != COMMAND:
        return None
    if char == "#" and at_token_start:
        end = text.find("\n", index)
        return Span(COMMENT, index, len(text) if end == -1 else end, True)
    for operator, kind in COMMAND_OPERATORS:
        if text.startswith(operator, index):
            return Span(kind, index, index + len(operator), True)
    return None


def scan(text, index, context, closer=None):
    """Returns (spans, end): the spans from index up to the context's closer, and the index just past it; end is None when the closer never comes and len(text) when there is none to find."""
    found, word, depth, boundary = [], index, 0, True
    while index < len(text):
        char = text[index]
        if char == closer and depth == 0:
            break
        if char not in CONSTRUCT_HEADS:
            index += 1
            continue
        span = construct(text, index, context, text[index - 1] in WHITESPACE if word < index else boundary)
        if span is None:
            index += 1
            continue
        if word < index:
            found.append(Span(WORD, word, index, True))
            boundary = text[index - 1] in WHITESPACE
        if span.kind == OPERATOR and text[index] == "(":
            depth += 1
        elif span.kind == OPERATOR and text[index] == ")" and depth:
            depth -= 1
        if span.kind in TOKEN_BOUNDARIES:
            boundary = True
        elif not line_continuation(text, span):
            boundary = False
        found.append(span)
        index = word = span.end
    if word < index:
        found.append(Span(WORD, word, index, True))
    if index < len(text):
        return found, index + 1
    return found, len(text) if closer is None else None


def line_continuation(text, span):
    return span.kind == ESCAPE and text[span.start + 1] == "\n"


def spans(text, context=COMMAND):
    return scan(text, 0, context)[0]


def body(text, span):
    return text[span.start + BODY_OPENER[span.kind] : span.end - 1 if span.closed else span.end]


def unescaped(chunk, in_double_quotes):
    if chunk[1] == "\n":
        return ""
    if in_double_quotes:
        return chunk[1:] if chunk[1] in '\\"' else chunk
    return chunk if chunk[1] in "$`" else chunk[1:]


def ansi_decoded(inner):
    """The text of a $'…' body with its escapes decoded as bash 3.2 does, ended at a NUL."""
    out, index = [], 0
    while index < len(inner):
        char = inner[index]
        if char != "\\" or index + 1 == len(inner):
            out.append(char)
            index += 1
            continue
        following, octal, hexadecimal = inner[index + 1], ANSI_OCTAL.match(inner, index + 1), ANSI_HEX.match(inner, index + 1)
        if following in ANSI_SIMPLE_ESCAPES:
            decoded, length = ANSI_SIMPLE_ESCAPES[following], 2
        elif octal:
            decoded, length = chr(int(octal.group(), 8) & 0xFF), 1 + len(octal.group())
        elif hexadecimal:
            decoded, length = chr(int(hexadecimal.group(1), 16)), 1 + len(hexadecimal.group())
        elif following == "c" and index + 2 < len(inner):
            decoded, length = chr(ord(inner[index + 2].upper()) & 0x1F), 3
        elif following == "c":
            decoded, length = "\\", 2
        else:
            decoded, length = "\\" + following, 2
        if decoded == "\0":
            break
        out.append("\\" + decoded if decoded in ("$", "`") else decoded)
        index += length
    return "".join(out)


def double_quote_removed(inner):
    out = []
    for span in spans(inner, DOUBLE):
        chunk = inner[span.start : span.end]
        out.append(unescaped(chunk, True) if span.kind == ESCAPE else chunk)
    return "".join(out)


def quote_removed(text, span):
    inner = body(text, span)
    if span.kind == DOUBLE:
        return double_quote_removed(inner)
    return ansi_decoded(inner) if span.kind == ANSI else inner


def delimiter_line_end(command, start, delimiter):
    """Where the line closing the heredoc ends, or the end of the command when the delimiter never comes."""
    position = start
    while position < len(command):
        line_end = command.find("\n", position)
        stop = len(command) if line_end == -1 else line_end
        if command[position:stop].strip() == delimiter:
            return stop
        if line_end == -1:
            break
        position = line_end + 1
    return len(command)


def fragment_token(text):
    """The token naming the program a piece of a segment runs."""
    _, tokens = strip_wrappers(tokenize(text))
    return tokens[0] if tokens else ""


def heredoc_readers(command, scanned, index):
    """Yields the program token of every stage the body of the heredoc operator at index reaches: the stage carrying it, then the pipeline's."""
    start = max((span.end for span in scanned if span.kind == OPERATOR and span.end <= index), default=0)
    yield fragment_token(command[start:index])
    stage, piped = [], False
    for span in scanned:
        if span.end <= index:
            continue
        chunk = command[span.start : span.end]
        if span.kind == OPERATOR:
            if chunk not in PIPE_OPERATORS:
                break
            if piped:
                yield fragment_token("".join(stage))
            stage, piped = [], True
        elif piped:
            stage.append(chunk)
    if piped:
        yield fragment_token("".join(stage))


def reads_as_script(token):
    """Whether the stage this program token names runs a heredoc body as a script: the token's basename is a shell, or the token begins with a variable or a substitution."""
    return os.path.basename(token) in SHELLS or bool(UNRESOLVABLE_PROGRAM.search(token))


def heredoc_bodies(command):
    """Yields (start, end, script) for every heredoc body: where it lies, and whether a stage in its pipeline runs it as a script."""
    scanned = spans(command)
    covered = 0
    for position, span in enumerate(scanned):
        if span.kind != HEREDOC_OPERATOR or span.start < covered:
            continue
        delimiter = heredoc_delimiter(command, scanned[position + 1 :])
        if delimiter is None or not HEREDOC_DELIMITER.match(delimiter):
            continue
        line_end = command.find("\n", span.end)
        if line_end == -1:
            continue
        covered = delimiter_line_end(command, line_end + 1, delimiter)
        yield line_end + 1, covered, any(reads_as_script(token) for token in heredoc_readers(command, scanned, span.start))


def heredocs_masked(command):
    """Returns (masked, scripts): the command with every heredoc body blanked, its length kept so offsets still address the command, and the text of every body a stage runs as a script."""
    masked, scripts = command, []
    for start, end, script in heredoc_bodies(command):
        masked = masked[:start] + " " * (end - start) + masked[end:]
        if script:
            scripts.append(command[start:end])
    return masked, scripts


def operator_parts(masked):
    """Returns [text, operator, text, …] split on the list operators and parentheses outside quotes, substitutions and comments; an unterminated span falls back to a plain split."""
    parts, current = [], []
    for span in spans(masked):
        if not span.closed:
            return SEGMENT_SPLIT.split(masked)
        chunk = masked[span.start : span.end]
        if span.kind == OPERATOR:
            parts.extend(("".join(current), chunk))
            current = []
        else:
            current.append(chunk)
    parts.append("".join(current))
    return parts


def split_pipelines(masked):
    """Groups the segments into pipelines: a segment joins the one before it when a | or |& lies between them."""
    pipelines, piped = [], False
    for index, part in enumerate(operator_parts(masked)):
        if index % 2:
            piped = piped or part in PIPE_OPERATORS
        elif part.strip():
            if piped and pipelines:
                pipelines[-1].append(part.strip())
            else:
                pipelines.append([part.strip()])
            piped = False
    return pipelines


def segment_offsets(masked):
    """Yields (offset, segment, enclosed): where each segment's text starts in the command, and whether a subshell's parentheses enclose it; a case pattern's ) reads as a subshell's, so parentheses that do not pair leave every segment enclosed."""
    parts = operator_parts(masked)
    paired = sum(part == "(" for part in parts[1::2]) == sum(part == ")" for part in parts[1::2])
    offset, depth = 0, 0
    for index, part in enumerate(parts):
        if index % 2:
            depth = max(0, depth + (part == "(") - (part == ")"))
        elif part.strip():
            yield offset + len(part) - len(part.lstrip()), part.strip(), depth > 0 or not paired
        offset += len(part)


def tokenize(segment):
    """Splits a segment into words with quotes removed and comments dropped; an unterminated quote falls back to a whitespace split."""
    words, current = [], None
    for span in spans(segment):
        chunk = segment[span.start : span.end]
        if span.kind in QUOTES and not span.closed:
            return segment.split()
        if span.kind == COMMENT:
            continue
        if span.kind == WORD or (span.kind == OPERATOR and chunk == "\n"):
            for char in chunk:
                if char not in WHITESPACE:
                    current = (current or "") + char
                elif current is not None:
                    words.append(current)
                    current = None
            continue
        piece = quote_removed(segment, span) if span.kind in QUOTES else unescaped(chunk, False) if span.kind == ESCAPE else chunk
        if piece or span.kind in QUOTES:
            current = (current or "") + piece
    if current is not None:
        words.append(current)
    return words


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


def command_substitutions(text, source, context=COMMAND):
    """Yields the command of every substitution the shell runs; text is scanned and source, of the same length, is read, so a substitution a heredoc body carries is text."""
    for span in spans(text, context):
        if span.kind == BACKTICK:
            yield BACKTICK_ESCAPE.sub(r"\1", body(source, span))
        elif span.kind in (SUBSTITUTION, PROCESS):
            yield body(source, span)
        elif span.kind == DOUBLE:
            yield from command_substitutions(body(text, span), body(source, span), DOUBLE)
        elif span.kind == EXPANSION:
            yield from command_substitutions(body(text, span), body(source, span), expansion_context(context))


def substitutions(masked, command):
    return command_substitutions(masked, command)


def nested_commands(tokens):
    """Yields command strings a shell would evaluate from within this segment."""
    if program(tokens) in SHELLS:
        for index, token in enumerate(tokens[1:-1], start=1):
            if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
                yield tokens[index + 1]
                break
    elif program(tokens) == "eval":
        yield " ".join(tokens[1:])


def located_segments(command, depth=0):
    """Yields (wrappers, tokens, segment, remainder, nested) for every segment, including shell indirection; segment is its text, remainder the enclosing command from the segment on, nested whether a subshell, a substitution or a shell string runs it."""
    if depth > MAX_DEPTH:
        return
    masked, scripts = heredocs_masked(command)
    for offset, segment, enclosed in segment_offsets(masked):
        wrappers, tokens = strip_wrappers(tokenize(segment))
        yield wrappers, tokens, segment, command[offset:], depth > 0 or enclosed
        for nested in nested_commands(tokens):
            yield from located_segments(nested, depth + 1)
    for script in scripts:
        yield from located_segments(script, depth + 1)
    for substitution in substitutions(masked, command):
        yield from located_segments(substitution, depth + 1)


def segments(command, depth=0):
    """Yields (wrappers, tokens) for every segment, including shell indirection."""
    for wrappers, tokens, _, _, _ in located_segments(command, depth):
        yield wrappers, tokens


def pipelines(command, depth=0):
    """Yields each pipeline as a list of (wrappers, tokens) stages, including shell indirection."""
    if depth > MAX_DEPTH:
        return
    masked, scripts = heredocs_masked(command)
    for pipeline in split_pipelines(masked):
        stages = [strip_wrappers(tokenize(segment)) for segment in pipeline]
        yield stages
        for _, tokens in stages:
            for nested in nested_commands(tokens):
                yield from pipelines(nested, depth + 1)
    for script in scripts:
        yield from pipelines(script, depth + 1)
    for substitution in substitutions(masked, command):
        yield from pipelines(substitution, depth + 1)


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


def heredoc_delimiter(text, following):
    """Returns the word after a heredoc operator with its quotes removed, or None when there is none or a quote never closes."""
    parts = []
    for span in following:
        chunk = text[span.start : span.end]
        if span.kind == WORD:
            if not parts:
                chunk = chunk.lstrip(WHITESPACE)
                if not chunk:
                    continue
            head = WORD_HEAD.match(chunk).group()
            parts.append(head)
            if len(head) < len(chunk):
                break
        elif span.kind in QUOTES:
            if not span.closed:
                return None
            parts.append(quote_removed(text, span))
        elif span.kind == ESCAPE:
            parts.append(unescaped(chunk, False))
        else:
            break
    return "".join(parts) if parts else None


def opens_heredoc(segment):
    """True when the segment carries << or <<- followed by a delimiter word."""
    scanned = spans(segment)
    for position, span in enumerate(scanned):
        if span.kind == HEREDOC_OPERATOR:
            delimiter = heredoc_delimiter(segment, scanned[position + 1 :])
            if delimiter is not None and HEREDOC_DELIMITER.match(delimiter):
                return True
    return False


def message_from_bare_stdin(args, segment):
    reads_stdin = any(letter == "F" and value == "-" for _, letter, value in commit_options(args))
    return reads_stdin and not opens_heredoc(segment)


def heredoc_body(remainder):
    match = HEREDOC.search(remainder)
    return match.group(3) if match else ""


def readable_message_texts(args, remainder):
    """Yields the message text the guard can read."""
    for _, letter, value in commit_options(args):
        if letter == "m":
            yield value
        elif letter == "F" and value == "-":
            yield heredoc_body(remainder)


def first_line(text):
    return next((line for line in text.splitlines() if line.strip()), None)


def unqualified_section_sign(text):
    return any(SPEC_BEFORE_SECTION.search(text[max(0, index - SECTION_LOOKBACK) : index]) is None for index, char in enumerate(text) if char == "§")


def check_commit_message(args, remainder):
    texts = list(readable_message_texts(args, remainder))
    subject = first_line(texts[0]) if texts else None
    if subject is not None and not CONVENTIONAL_SUBJECT.match(subject):
        return deny("commit subjects follow Conventional Commits: <type>(<scope>): <description>.", f"types {CONVENTIONAL_TYPES}.")
    if any(unqualified_section_sign(text) for text in texts):
        return deny("a bare § is an internal reference; commit messages stand alone.", "qualify it: RFC 6749 §3.1.1, OIDC Core §3.1.2.1.")
    return None


def target_end(segment, following):
    """Where the word a redirection writes to ends."""
    started = False
    for span in following:
        if span.kind in TOKEN_BOUNDARIES:
            return span.start
        if span.kind == WORD:
            for offset, char in enumerate(segment[span.start : span.end]):
                if char not in WHITESPACE:
                    started = True
                elif started:
                    return span.start + offset
        else:
            started = True
    return len(segment)


def descriptor_start(segment, index):
    """Where the file descriptor a redirection carries begins, else the operator's own start."""
    start = index
    while start and segment[start - 1].isdigit():
        start -= 1
    return start if start < index and (start == 0 or segment[start - 1] in WHITESPACE) else index


def redirections_removed(segment):
    """The segment's text with each redirection, its file descriptor and its target word taken out."""
    scanned = spans(segment)
    kept, end = [], 0
    for position, span in enumerate(scanned):
        if span.kind != REDIRECTION:
            continue
        kept.append(segment[end : descriptor_start(segment, span.start)])
        end = target_end(segment, scanned[position + 1 :])
    kept.append(segment[end:])
    return "".join(kept).strip()


def check_git(subcommand, args, global_options, cwd, text):
    """text is the segment's own text; None when a subshell, a substitution, a shell string or a find action runs it."""
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
        if text is None:
            return deny(
                "a push inside a subshell, a command substitution or a find action reaches the default branch with no prompt at all.",
                "git push origin <branch> as its own command.",
            )
        if not PUSH_COMMAND.match(redirections_removed(text)):
            return deny(
                "a push in any other form can reach the default branch without the prompt its name carries.",
                "git push origin <branch>.",
            )
        return None
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


class BudgetExhausted(Exception):
    pass


def run_git(arguments, deadline, stdin):
    """None when git is absent or one call outran its own timeout with budget left; a timeout at the deadline is exhaustion."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BudgetExhausted
    try:
        return subprocess.run(arguments, input=stdin, capture_output=True, timeout=min(remaining, GIT_TIMEOUT_SECONDS))
    except subprocess.TimeoutExpired:
        if time.monotonic() >= deadline:
            raise BudgetExhausted
        return None
    except OSError:
        return None


def ignoring_patterns(root, paths, deadline):
    """Path to the pattern check-ignore -v reports for it; a path it reports nothing for is absent."""
    stdin = b"".join(os.fsencode(path) + b"\0" for path in paths if "\0" not in path)
    completed = run_git(["git", "-C", root, "check-ignore", "-v", "-z", "--stdin", "--"], deadline, stdin)
    if completed is None or completed.returncode != 0:
        return {}
    # check-ignore -v -z writes source NUL line NUL pattern NUL path NUL per match.
    fields = completed.stdout.split(b"\0")[:-1]
    return {os.fsdecode(fields[index + 3]): os.fsdecode(fields[index + 2]) for index in range(0, len(fields) - 3, 4)}


def repository_path(target, cwd, root):
    resolved = os.path.normpath(os.path.join(cwd, target))
    if resolved == root or not under_prefix(resolved, root) or os.path.islink(resolved):
        return None
    return os.path.relpath(resolved, root)


def unresolvable_delete(targets):
    return any(UNRESOLVABLE_TARGET.search(target) for target in targets)


def deletable_targets(targets, cwd, deadline):
    resolved = [target for target in map(resolve_rm_target, targets) if not under_safe_prefix(target)]
    if not resolved:
        return True
    root = repo_root(cwd)
    if root is None:
        return False
    root = os.path.normpath(root)
    paths = [repository_path(target, cwd, root) for target in resolved]
    if None in paths:
        return False
    patterns = ignoring_patterns(root, paths, deadline)
    # A negated match is not ignored: test_a_negated_pattern_does_not_make_a_path_deletable.
    return all(path in patterns and not patterns[path].startswith("!") for path in paths)


def deny_unresolvable_delete():
    return deny("delete target carries a shell substitution the guard cannot resolve.", "name the path literally.")


def deny_rm():
    return deny(
        "rm outside $TMPDIR, the scratchpad or a git-ignored path deletes work the tree cannot regenerate.",
        "mv <target> $TMPDIR/<name> — nothing is lost and the user can inspect it; a git-ignored path inside the repository may be deleted in place.",
    )


def deny_budget():
    return deny(
        f"the guard's {BUDGET_SECONDS} s budget ran out before every delete target was judged.",
        "fewer delete targets or segments per command; a git-ignored path inside the repository may be deleted in place.",
    )


def rm_targets(args):
    if "--" in args:
        separator = args.index("--")
        return [arg for arg in args[:separator] if not arg.startswith("-")] + args[separator + 1 :]
    return [arg for arg in args if not arg.startswith("-")]


def check_rm(wrappers, tokens, cwd, deadline):
    if program(tokens) != "rm":
        return None
    targets = rm_targets(tokens[1:])
    if "xargs" in wrappers or unresolvable_delete(targets):
        return deny_unresolvable_delete()
    if deletable_targets(targets, cwd, deadline):
        return None
    return deny_rm()


def find_parts(args):
    """Returns (global flags, start paths, expression); no start path means the current directory."""
    flags, paths, index = [], [], 0
    while index < len(args):
        arg = args[index]
        if arg == "-f" and index + 1 < len(args):
            paths.append(args[index + 1])
            index += 2
        elif arg in FIND_GLOBAL_FLAGS:
            flags.append(arg)
            index += 1
        elif arg.startswith("-") or arg in ("(", "!"):
            break
        else:
            paths.append(arg)
            index += 1
    return flags, paths or ["."], args[index:]


def find_action_end(args, index):
    if args[index] == "-delete":
        return index + 1
    return next((position + 1 for position in range(index + 1, len(args)) if args[position] in FIND_ACTION_TERMINATORS), len(args))


def find_action_commands(args):
    """Yields (action, command) for each -exec, -execdir, -ok or -okdir."""
    index = 0
    while index < len(args):
        if args[index] in FIND_EXEC_ACTIONS:
            end = find_action_end(args, index)
            yield args[index], shlex.join([token for token in args[index + 1 : end] if token not in FIND_ACTION_TERMINATORS])
            index = end
        else:
            index += 1


def find_action_segments(args):
    """Yields (action, wrappers, tokens) for every segment an action runs, including shell indirection."""
    for action, command in find_action_commands(args):
        for wrappers, tokens in segments(command):
            yield action, wrappers, tokens


def find_deletes(args):
    if "-delete" in args:
        return True
    return any(program(tokens) == "rm" or (program(tokens) == "find" and find_deletes(tokens[1:])) for _, _, tokens in find_action_segments(args))


def find_action_git_decision(tokens, cwd):
    invocation = git_invocation(tokens)
    if invocation is None:
        return None
    subcommand, args, _ = invocation
    decision = check_git(*invocation, cwd, None)
    if decision is not None:
        return decision
    if subcommand == "commit" or (subcommand in ("checkout", "restore") and any(FIND_MATCH in spec for spec in pathspecs(args))):
        return deny(f"git {subcommand} inside a find action cannot be judged.", f"run git {subcommand} as its own command with -- <paths>.")
    return None


def find_action_rm_decision(action, wrappers, tokens, cwd, deadline):
    if program(tokens) != "rm":
        return None
    decision = check_rm(wrappers, [token for token in tokens if token != FIND_MATCH], cwd, deadline)
    if decision is not None:
        return decision
    targets = [target for target in rm_targets(tokens[1:]) if target != FIND_MATCH]
    if any(FIND_MATCH in target for target in targets) or (action in FIND_DIR_ACTIONS and not all(os.path.isabs(resolve_rm_target(target)) for target in targets)):
        return deny_rm()
    return None


def find_action_decision(args, cwd, deadline):
    for action, wrappers, tokens in find_action_segments(args):
        decision = find_action_git_decision(tokens, cwd) or find_action_rm_decision(action, wrappers, tokens, cwd, deadline) or check_find(tokens, cwd, deadline)
        if decision is not None:
            return decision
    return None


def find_shape(expression):
    """Returns (name values, wants directories) when the expression is allowed primaries then one unprompted action, else None."""
    names, directory, index = [], False, 0
    while index < len(expression) and expression[index] not in FIND_ACTIONS:
        token = expression[index]
        value = expression[index + 1] if index + 1 < len(expression) else None
        if token == "-type" and value in FIND_TYPES:
            directory = directory or value == "d"
            index += 2
        elif token in FIND_NAME_PRIMARIES and value is not None:
            names.append(value)
            index += 2
        elif token in FIND_DEPTH_PRIMARIES and value is not None and value.isdigit():
            index += 2
        elif token in FIND_BARE_PRIMARIES:
            index += 1
        else:
            return None
    if not names or index == len(expression) or expression[index] not in FIND_UNPROMPTED_ACTIONS or find_action_end(expression, index) != len(expression):
        return None
    return names, directory


def inside_repository(target, cwd, root):
    return under_prefix(os.path.realpath(os.path.join(cwd, resolve_rm_target(target))), os.path.realpath(root))


def unanchored(pattern):
    body = pattern
    while body.startswith(("/**/", "**/")):
        body = body.removeprefix("/**/").removeprefix("**/")
    return not pattern.startswith("!") and "/" not in body[:-1]


def exempt_names(root, names, directory, deadline):
    """A dir/ pattern matches an absent name only with the trailing slash."""
    retries = {name: name + "/" for name in names if directory and not name.endswith("/")}
    patterns = ignoring_patterns(root, names + list(retries.values()), deadline)
    found = [patterns.get(name) if name in patterns or name not in retries else patterns.get(retries[name]) for name in names]
    return all(pattern is not None and unanchored(pattern) for pattern in found)


def exempt_find(starts, names, directory, cwd, deadline):
    root = repo_root(cwd)
    return root is not None and all(inside_repository(start, cwd, root) for start in starts) and exempt_names(root, names, directory, deadline)


def check_find(tokens, cwd, deadline):
    if program(tokens) != "find":
        return None
    args = tokens[1:]
    decision = find_action_decision(args, cwd, deadline)
    if decision is not None or not find_deletes(args):
        return decision
    flags, starts, expression = find_parts(args)
    if unresolvable_delete(starts):
        return deny_unresolvable_delete()
    if not FIND_FOLLOW_FLAGS.isdisjoint(flags):
        return deny_rm()
    if deletable_targets(starts, cwd, deadline):
        return None
    shape = find_shape(expression)
    if shape is None:
        return deny_rm()
    names, directory = shape
    if any(UNRESOLVABLE_NAME.search(name) for name in names):
        return deny_unresolvable_delete()
    return None if exempt_find(starts, names, directory, cwd, deadline) else deny_rm()


def without_version(name):
    return name if name.startswith("@") else name.split("@", 1)[0]


def package_script(tokens):
    """Returns the script an npm/yarn/pnpm invocation runs (test for the shorthand), else None."""
    if program(tokens) not in PACKAGE_MANAGERS:
        return None
    rest = skip_options(tokens[1:], PACKAGE_MANAGER_OPTIONS_WITH_VALUE)
    if rest and rest[0] in ("test", "t"):
        return "test"
    if not rest or rest[0] != "run":
        return None
    script = skip_options(rest[1:], PACKAGE_MANAGER_OPTIONS_WITH_VALUE)
    return script[0] if script else None


def npx_target(tokens):
    rest = skip_options(tokens[1:], NPX_OPTIONS_WITH_VALUE)
    return without_version(os.path.basename(rest[0])) if rest else None


def python_module(tokens):
    rest = tokens[1:]
    while rest and rest[0].startswith("-"):
        if rest[0] == "-m":
            return rest[1] if len(rest) > 1 else None
        rest = rest[2:] if rest[0] in PYTHON_OPTIONS_WITH_VALUE else rest[1:]
    return None


def first_argument(tokens):
    rest = [token for token in tokens[1:] if not token.startswith("+")]
    return rest[0] if rest else None


def make_targets(tokens):
    return [token for token in tokens[1:] if not token.startswith("-") and "=" not in token]


def runs_tests_script(tokens):
    scripts = [token for token in tokens[1:] if not token.startswith("-")]
    return bool(scripts) and "tests" in os.path.normpath(scripts[0]).split("/")


def is_verify_run(tokens):
    name = program(tokens)
    script = package_script(tokens)
    if script is not None:
        return VERIFY_SCRIPT.match(script) is not None
    if name == "npx":
        return npx_target(tokens) in JS_RUNNERS
    if PYTHON.match(name):
        return python_module(tokens) in PYTHON_TEST_MODULES
    if name in ("go", "cargo"):
        return first_argument(tokens) == "test"
    if name == "make":
        return any(target in MAKE_VERIFY_TARGETS for target in make_targets(tokens))
    if name == "bash":
        return runs_tests_script(tokens)
    return name in JS_RUNNERS or name == "pytest"


def verify_pipe_decision(command):
    for stages in pipelines(command):
        for position, (_, tokens) in enumerate(stages):
            if is_verify_run(tokens) and any(program(later) in PAGERS for _, later in stages[position + 1 :]):
                return deny(
                    "piping a test or verify run through tail or head hides the runner's summary.",
                    'redirect: <command> > "$TMPDIR/out.txt" 2>&1, then read the file.',
                )
    return None


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
    deadline = time.monotonic() + BUDGET_SECONDS

    for wrappers, tokens, segment, remainder, nested in located_segments(command):
        invocation = git_invocation(tokens)
        if invocation is not None:
            subcommand, args, global_options = invocation
            decision = check_git(subcommand, args, global_options, cwd, None if nested else segment)
            if decision is not None:
                return decision
            if subcommand == "commit":
                commits = True
                if message_from_bare_stdin(args, segment):
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
                decision = check_commit_message(args, remainder)
                if decision is not None:
                    return decision
        try:
            decision = check_rm(wrappers, tokens, cwd, deadline) or check_find(tokens, cwd, deadline)
        except BudgetExhausted:
            return deny_budget()
        if decision is not None:
            return decision

    return verify_pipe_decision(command) or (attribution_decision(command) if commits else None)


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
