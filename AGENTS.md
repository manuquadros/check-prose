# AGENTS.md

`check-prose`: a review aid listing long docstrings and comment blocks in
code a diff touches. `README.md` owns what it does and why; the module
docstring of `src/check_prose/__init__.py` owns nothing beyond a summary.

## Working here

```bash
pdm install
pdm run test        # pytest
pdm run lint        # ruff check .
pdm run typecheck   # mypy src/ (strict)
```

Run all three before committing.

## Tickets

`tickets/` is the backlog, managed by ticketkit (a dev dependency):
`pdm run tickets` ranks it, `--file <payload>.json` files one,
`--claim` / `--release` stamp a claim. A fix `git rm`s its shard in the
fix commit; closing without a fix uses `--close <slug> --reason`.

## Commits

Trunk-based on `main`. The global conventions apply unchanged, including
showing the message and waiting for a go-ahead.
