#!/usr/bin/env python3
"""
Rewrite PHP include/require calls from:
    include('file.php');
to:
    include 'file.php';

Only rewrites lines where the ONLY code on the line is a single include/require
statement (plus whitespace and PHP comments). If there's any other code on the
line, it is left unchanged.

Default behavior:
  - If no files are provided: process all *.php files in the current directory
    and subdirectories.
  - If one or more file paths are provided: process ONLY those files.

Usage:
  python3 replace-php-includes.py
  python3 replace-php-includes.py --dry-run
  python3 replace-php-includes.py --no-backup
  python3 replace-php-includes.py path/to/a.php b.php
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple


# Matches a full-line statement (optionally with trailing comments/whitespace).
# Captures: indent, keyword, argument, trailing
STMT_RE = re.compile(
    r"""
    ^(\s*)                                           # indent
    (include|include_once|require|require_once)      # keyword
    \s*\(\s*(.*?)\s*\)\s*;                           # ( arg );
    (\s*(?:(?://|\#|/\*).*)?\s*(?:\?>\s*)?)$         # trailing: ws + optional comment + optional ?>
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class CommentState:
    """Tracks whether we are currently inside a multi-line /* ... */ comment."""
    in_block: bool = False


def strip_comments_for_code_check(line: str, state: CommentState) -> Tuple[str, CommentState]:
    """
    Remove PHP comments from the line (outside of strings) to detect if there is any extra code.
    Supports //, #, and /* ... */ (including multi-line block comments via state).
    Returns (code_without_comments, new_state).
    """
    i = 0
    n = len(line)
    out = []
    in_single = False
    in_double = False
    escaped = False

    while i < n:
        ch = line[i]
        nxt = line[i + 1] if i + 1 < n else ""

        if state.in_block:
            # Consume until end of block comment
            if ch == "*" and nxt == "/":
                state.in_block = False
                i += 2
                continue
            i += 1
            continue

        # Handle escaping inside strings
        if (in_single or in_double) and not escaped and ch == "\\":
            escaped = True
            out.append(ch)
            i += 1
            continue

        # Toggle string states (only when not escaped)
        if not escaped:
            if not in_double and ch == "'":
                in_single = not in_single
                out.append(ch)
                i += 1
                continue
            if not in_single and ch == '"':
                in_double = not in_double
                out.append(ch)
                i += 1
                continue

        # Reset escape after consuming a character in string context
        if escaped:
            escaped = False
            out.append(ch)
            i += 1
            continue

        # If not inside a string, detect comment starts
        if not in_single and not in_double:
            if ch == "/" and nxt == "/":
                break  # rest is // comment
            if ch == "#":
                break  # rest is # comment
            if ch == "/" and nxt == "*":
                state.in_block = True
                i += 2
                continue

        out.append(ch)
        i += 1

    return "".join(out), state


def line_is_safe_single_statement(original_line: str, state: CommentState) -> Tuple[bool, bool, CommentState]:
    """
    Determine if a line contains ONLY one include/require(...) statement + comments/whitespace.
    Returns:
      - is_safe: can rewrite
      - matches_stmt: line matches include/require(...) syntactically
      - new_state: updated block comment state after scanning the line
    """
    m = STMT_RE.match(original_line)
    matches_stmt = m is not None

    # Remove comments to see if any extra code exists besides the statement
    code_wo_comments, new_state = strip_comments_for_code_check(
        original_line, CommentState(state.in_block)
    )

    # If it doesn't even match the statement form, we cannot rewrite
    if not matches_stmt:
        return False, False, new_state

    # Now check: after stripping comments, the remaining code must be exactly that statement
    # (possibly different spacing/casing, but still only include/require + parentheses + arg + ;)
    # We'll do a lenient regex on the comment-stripped code.
    code = code_wo_comments.strip()
    # Allow a closing PHP tag at the end of the line
    code = re.sub(r"\s*\?>\s*$", "", code)
    safe = bool(
        re.match(
            r"^(include|include_once|require|require_once)\s*\(\s*.*?\s*\)\s*;\s*$",
            code,
            re.IGNORECASE,
        )
    )

    return safe, True, new_state


def rewrite_line_if_needed(line: str) -> str:
    """Rewrite include/require with parentheses into keyword + space + arg + ; keeping trailing comments AND EOL."""
    # Preserve original end-of-line exactly
    eol = ""
    if line.endswith("\r\n"):
        eol = "\r\n"
        core = line[:-2]
    elif line.endswith("\n"):
        eol = "\n"
        core = line[:-1]
    else:
        core = line

    m = STMT_RE.match(core)
    if not m:
        return line

    indent, kw, arg, trailing = m.groups()

    # Keep original keyword casing as in source (kw is matched as-is by regex)
    # Normalize to: "<indent><kw> <arg>;<trailing>"
    # trailing already includes its leading whitespace (if any)
    return f"{indent}{kw} {arg};{trailing}{eol}"


def process_file(path: str, dry_run: bool, backup: bool) -> Tuple[int, int]:
    """Return (changed_lines, total_lines)."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    changed = 0
    total = len(lines)
    out_lines = []

    state = CommentState(in_block=False)

    for line in lines:
        is_safe, matches_stmt, state = line_is_safe_single_statement(line, state)

        if is_safe and matches_stmt:
            new_line = rewrite_line_if_needed(line)
            if new_line != line:
                changed += 1
            out_lines.append(new_line)
        else:
            out_lines.append(line)

    if changed and not dry_run:
        if backup:
            bak_path = path + ".bak"
            if not os.path.exists(bak_path):
                with open(bak_path, "w", encoding="utf-8", errors="replace") as b:
                    b.writelines(lines)

        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.writelines(out_lines)

    return changed, total


def iter_php_files_under_current_dir() -> Iterable[str]:
    """Yield all *.php files under current directory recursively."""
    for root, _, files in os.walk("."):
        for name in files:
            if name.lower().endswith(".php"):
                yield os.path.join(root, name)


def normalize_input_files(paths: List[str]) -> List[str]:
    """
    Normalize user-provided file paths:
    - Keep only existing files
    - Warn on missing paths
    """
    out: List[str] = []
    for p in paths:
        norm = os.path.normpath(p)
        if not os.path.exists(norm):
            print(f"WARNING: path not found, skipped: {p}")
            continue
        if os.path.isdir(norm):
            print(f"WARNING: directory provided, skipped: {p}")
            continue
        out.append(norm)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite PHP include/require() to include/require without parentheses.")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify files, only report changes.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create .bak files.")
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional list of PHP files to process. If omitted, all *.php under current directory are processed.",
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    backup = not args.no_backup

    if args.files:
        targets = normalize_input_files(args.files)
        # Optional: if user passed a non-php file, still allow it, but warn.
        for t in targets:
            if not t.lower().endswith(".php"):
                print(f"NOTE: processing non-.php file because it was explicitly provided: {t}")
    else:
        targets = list(iter_php_files_under_current_dir())

    total_files = 0
    total_changed_files = 0
    total_changed_lines = 0

    for path in targets:
        total_files += 1
        try:
            changed_lines, _ = process_file(path, dry_run=dry_run, backup=backup)
        except OSError as e:
            print(f"ERROR: {path}: {e}")
            continue

        if changed_lines:
            total_changed_files += 1
            total_changed_lines += changed_lines
            print(f"{path}: changed {changed_lines} line(s)")

    if dry_run:
        print(f"\nDRY RUN: would change {total_changed_lines} line(s) across {total_changed_files}/{total_files} file(s).")
    else:
        print(f"\nDone: changed {total_changed_lines} line(s) across {total_changed_files}/{total_files} file(s).")
        if backup:
            print("Backups created as *.bak (only for files that actually changed).")


if __name__ == "__main__":
    main()
