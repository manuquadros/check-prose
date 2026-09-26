"""List long docstrings and comment blocks in the code a diff touches.

A review aid, not a gate: it points review at prose to re-read, including
prose the diff never edited. Given paths, it checks those files whole
instead. Exit codes: 0 nothing over the limits, or no Python file changed ·
1 prose over a limit · 2 could not run. Rationale: README.md.
"""

import argparse
import ast
import io
import os
import pathlib
import re
import subprocess
import sys
import tokenize
from typing import NamedTuple

# Docstring lines counted exclude blank lines and the sphinx field list.
MAX_DOCSTRING_LINES = 6
MAX_COMMENT_LINES = 3

# Fields close a docstring by convention here, so everything from the first
# one on is the field list.
_FIELD = re.compile(
    r"^\s*:(param|type|return|returns|rtype|raises|raise|yield|yields"
    r"|var|ivar|cvar)\b"
)
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

_Scope = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


class Finding(NamedTuple):
    """One stretch of prose over its limit.

    Fields: the file, the prose's first line, its counted length, and what
    it is (a named docstring or a comment block).
    """

    path: pathlib.Path
    line: int
    length: int
    kind: str


class CouldNotRun(Exception):
    """The diff or a file in it could not be read."""


def changed_lines(
    root: pathlib.Path, base: str
) -> dict[pathlib.Path, set[int]]:
    """Map each changed Python file to its changed lines in the worktree.

    A pure deletion marks the line just before it, so the definition that
    lost code still counts as touched.

    :param root: any directory inside the repository.
    :param base: revision to diff the worktree against.
    :return: absolute path of each changed, still existing file to the
        worktree line numbers the diff added, changed or deleted after.
    :raises CouldNotRun: when git cannot produce the diff.
    """
    git = ["git", "-C", str(root)]
    try:
        top = subprocess.run(
            [*git, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        diff = subprocess.run(
            [*git, "diff", "-U0", "--no-color", "--no-ext-diff", base, "--"]
            + ["*.py"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise CouldNotRun(error.stderr.strip()) from error

    changed: dict[pathlib.Path, set[int]] = {}
    current: set[int] | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            path = pathlib.Path(top) / target.removeprefix("b/")
            current = (
                None
                if target == "/dev/null" or not path.exists()
                else changed.setdefault(path, set())
            )
        elif current is not None and (hunk := _HUNK.match(line)):
            start = int(hunk[1])
            count = 1 if hunk[2] is None else int(hunk[2])
            current.update(range(start, start + count) if count else [start])
    return changed


def whole_files(paths: list[pathlib.Path]) -> dict[pathlib.Path, set[int]]:
    """Map every Python file under `paths` to all of its lines.

    :param paths: files and directories to check whole.
    :return: absolute path of each Python file to every line number in it.
    :raises CouldNotRun: when a path does not exist or no Python file is
        found under any of them.
    """
    files: dict[pathlib.Path, set[int]] = {}
    for path in paths:
        if not path.exists():
            raise CouldNotRun(f"{path} does not exist")
        found = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for file in found:
            lines = len(file.read_text().splitlines())
            files[file.resolve()] = set(range(1, lines + 1))
    if not files:
        raise CouldNotRun(f"no Python file under {', '.join(map(str, paths))}")
    return files


def _span(node: _Scope) -> range:
    return range(node.lineno, (node.end_lineno or node.lineno) + 1)


def _prose_lines(docstring: str) -> int:
    count = 0
    for line in docstring.splitlines():
        if _FIELD.match(line):
            break
        count += bool(line.strip())
    return count


def _docstring_findings(
    path: pathlib.Path, tree: ast.Module, touched: set[int]
) -> list[Finding]:
    defs = [n for n in ast.walk(tree) if isinstance(n, _Scope)]
    # The module docstring is in scope when module-level code changed.
    module_level = {
        line
        for line in touched
        if not any(line in _span(node) for node in defs)
    }
    scopes: list[tuple[ast.Module | _Scope, str, set[int]]] = [
        (node, node.name, touched & set(_span(node))) for node in defs
    ]
    scopes.append((tree, "module", module_level))
    findings = []
    for node, name, in_scope in scopes:
        docstring = ast.get_docstring(node, clean=True)
        if not in_scope or docstring is None:
            continue
        length = _prose_lines(docstring)
        if length > MAX_DOCSTRING_LINES:
            line = node.body[0].lineno
            findings.append(Finding(path, line, length, f"docstring {name}"))
    return findings


def _comment_findings(
    path: pathlib.Path, source: str, tree: ast.Module, touched: set[int]
) -> list[Finding]:
    lines = source.splitlines()
    blocks: list[list[int]] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        row = token.start[0]
        if token.type != tokenize.COMMENT or row == 1:
            continue
        if not lines[row - 1].lstrip().startswith("#"):
            continue
        if blocks and blocks[-1][-1] == row - 1:
            blocks[-1].append(row)
        else:
            blocks.append([row])

    spans = [set(_span(n)) for n in ast.walk(tree) if isinstance(n, _Scope)]
    findings = []
    for block in blocks:
        rows = set(block)
        # A block inside a touched definition is in scope even if unedited.
        enclosing = [s for s in spans if rows <= s]
        in_scope = rows & touched or any(s & touched for s in enclosing)
        if in_scope and len(block) > MAX_COMMENT_LINES:
            findings.append(Finding(path, block[0], len(block), "comment"))
    return findings


def prose_findings(path: pathlib.Path, touched: set[int]) -> list[Finding]:
    """Docstrings and comment blocks over their limit in touched code.

    :param path: Python file to read.
    :param touched: its changed line numbers.
    :return: every over-limit docstring of a touched scope and every
        over-limit comment block inside a touched definition or edited
        itself.
    :raises CouldNotRun: when the file does not parse.
    """
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise CouldNotRun(f"{path}: {error}") from error
    return _docstring_findings(path, tree, touched) + _comment_findings(
        path, source, tree, touched
    )


def main() -> int:
    """Report over-limit prose in the diff, longest first.

    :return: the process exit code.
    """
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=pathlib.Path,
        help="files or directories to check whole, instead of a diff",
    )
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path.cwd(),
        help="repository whose diff to check; defaults to the current one",
    )
    parser.add_argument(
        "--base",
        help="revision to diff the worktree against; defaults to HEAD",
    )
    args = parser.parse_args()
    if args.paths and args.base:
        parser.error("give paths or --base, not both")
    base = args.base or "HEAD"
    try:
        changed = (
            whole_files(args.paths)
            if args.paths
            else changed_lines(args.root.resolve(), base)
        )
        findings = [
            finding
            for path, touched in sorted(changed.items())
            for finding in prose_findings(path, touched)
        ]
    except CouldNotRun as error:
        print(f"COULD NOT RUN: {error}", file=sys.stderr)
        return 2

    if not changed:
        print(f"NOT APPLICABLE: no Python file changed since {base}.")
        return 0
    for finding in sorted(findings, key=lambda f: -f.length):
        limit = (
            MAX_COMMENT_LINES
            if finding.kind == "comment"
            else MAX_DOCSTRING_LINES
        )
        print(
            f"{os.path.relpath(finding.path)}:{finding.line}: "
            f"{finding.kind}, "
            f"{finding.length} lines (limit {limit})"
        )
    if findings:
        print(
            f"\n{len(findings)} over the limit in {len(changed)} checked "
            f"files; re-read each claim, then cut or move it to docs/."
        )
        return 1
    print(f"PASSED: no long prose in {len(changed)} checked files.")
    return 0
