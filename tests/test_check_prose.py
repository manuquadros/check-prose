"""``check-prose``: the review aid listing long prose in touched code.

Run against throwaway repositories, so each diff is staged exactly.
"""

import os
import pathlib
import subprocess
import sys

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}

_LONG_DOC = '    """Summary.\n\n' + "    Prose.\n" * 7 + '    """\n'
_SHORT_DOC = '    """Summary."""\n'


def _repo(root: pathlib.Path, source: str) -> pathlib.Path:
    """A repository whose single commit holds `lib.py` with `source`."""
    for command in (
        ["init", "-q"],
        ["add", "lib.py"],
        ["commit", "-q", "-m", "init"],
    ):
        if command[0] == "add":
            (root / "lib.py").write_text(source)
        subprocess.run(
            ["git", "-C", str(root), *command], check=True, env=_GIT_ENV
        )
    return root


def _run(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "check_prose", "--root", str(root), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _source(doc: str, body: str = "    return 1\n") -> str:
    return f"def touched():\n{doc}{body}\n\ndef other():\n{_LONG_DOC}    pass\n"


def test_unedited_long_docstring_of_a_touched_def_is_listed(
    tmp_path: pathlib.Path,
) -> None:
    """The point of the tool: inherited prose in edited code gets re-read,
    while the equally long docstring of an untouched def stays out."""
    root = _repo(tmp_path, _source(_LONG_DOC))
    (root / "lib.py").write_text(_source(_LONG_DOC, "    return 2\n"))

    result = _run(root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "docstring touched, 8 lines" in result.stdout
    assert "other" not in result.stdout


def test_field_list_does_not_count(tmp_path: pathlib.Path) -> None:
    """`:param:` and friends are required here; only prose above them is
    counted, so a short summary with many fields passes."""
    fields = "    :param x: a.\n" * 10 + "    :return: b.\n"
    doc = '    """Summary.\n\n' + fields + '    """\n'
    root = _repo(tmp_path, _source(doc))
    (root / "lib.py").write_text(_source(doc, "    return 2\n"))

    result = _run(root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_long_comment_block_in_touched_def_is_listed(
    tmp_path: pathlib.Path,
) -> None:
    """A comment block counts even when the edit was elsewhere in the def."""
    body = "    # why\n" * 4 + "    return 1\n"
    root = _repo(tmp_path, _source(_SHORT_DOC, body))
    (root / "lib.py").write_text(
        _source(_SHORT_DOC, body.replace("return 1", "return 2"))
    )

    result = _run(root)

    assert result.returncode == 1
    assert "comment, 4 lines" in result.stdout


def test_no_python_change_is_not_applicable(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path, _source(_LONG_DOC))

    result = _run(root)

    assert result.returncode == 0
    assert "NOT APPLICABLE" in result.stdout


def test_unknown_base_could_not_run(tmp_path: pathlib.Path) -> None:
    """A diff git cannot compute is a coverage hole, never a clean pass."""
    root = _repo(tmp_path, _source(_LONG_DOC))

    result = _run(root, "--base", "no-such-ref")

    assert result.returncode == 2
    assert "COULD NOT RUN" in result.stderr


def test_paths_check_whole_files_without_a_diff(
    tmp_path: pathlib.Path,
) -> None:
    """A named file is reviewed whole: every def is in scope, committed or
    not."""
    root = _repo(tmp_path, _source(_LONG_DOC))

    result = _run(root, str(root / "lib.py"))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "docstring touched" in result.stdout
    assert "docstring other" in result.stdout


def test_path_with_no_python_file_could_not_run(
    tmp_path: pathlib.Path,
) -> None:
    """An empty selection checked nothing; it must not read as clean."""
    (tmp_path / "empty").mkdir()

    result = _run(tmp_path, str(tmp_path / "empty"))

    assert result.returncode == 2
    assert "COULD NOT RUN" in result.stderr
