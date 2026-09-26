# check-prose

Lists the docstrings and comment blocks that are over a line limit inside
the code a diff touches, longest first, so a reviewer re-reads them.

```bash
check-prose                        # the working tree against HEAD
check-prose --base main            # everything since main
check-prose src/pkg/mod.py src/pkg/sub/   # whole files, no diff
check-prose --root ../other-repo   # another repository's diff
```

## Why

Prose that describes code goes false when the code changes under it and
nobody re-reads it. A diff shows the lines someone edited; the docstring
three lines above, which still describes the old behaviour, is not in it.
So a docstring or comment block is listed when it sits inside any function
or class the diff touches, edited or not. Long prose is where this costs
most: each sentence is a claim, and each claim can be wrong.

It is a review aid, not a gate. The fix for a finding is to re-check every
claim the prose makes against the current code, then cut what a test, a
type or a clearer name could carry instead. Trimming a docstring until it
fits under the limit fixes nothing.

## What counts

- A docstring's non-blank lines, up to its first sphinx field
  (`:param:`, `:return:`, `:raises:`, …). The field list is excluded, so
  a codebase that requires complete fields is not penalised for them.
  Fields are assumed to close the docstring.
- A block of consecutive full-line `#` comments. Trailing comments after
  code and a line-1 shebang are ignored.
- The limits are `MAX_DOCSTRING_LINES` and `MAX_COMMENT_LINES` in
  `src/check_prose/__init__.py`.

A module docstring is in scope when module-level code changed. A comment
block is in scope when it was edited itself or sits inside a touched
function or class.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | nothing over a limit, or no Python file changed (`NOT APPLICABLE`) |
| 1 | prose over a limit, listed as `path:line: kind, N lines (limit L)` |
| 2 | `COULD NOT RUN`: a revision git does not know, a file that does not parse, or paths holding no Python file |

## Install

```bash
pdm add -dG dev "check-prose @ git+https://github.com/manuquadros/check-prose"
```

Wire it as a pdm script in the consuming repo if you want a short name:
`check-prose = "check-prose"`.
