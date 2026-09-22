## What this changes

<!-- A sentence or two. If it changes the public surface, say so plainly: this is the reference
     SDK, and the TypeScript, Java, Ruby, and PHP ports follow its shape. -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run mypy` passes
- [ ] New behavior has a test, or the fix has one that failed before it
- [ ] `uv.lock` is committed, if dependencies changed
- [ ] `CHANGELOG.md` has an entry under Unreleased, for anything user-visible
