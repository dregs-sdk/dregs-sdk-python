# Contributing

Thanks for helping improve the Dregs Python SDK.

This is the **reference** SDK: the SDKs for TypeScript, Java, Ruby, and PHP are ported from this
one's shape. A change to the public surface here is a change to all of them, so surface changes
are worth discussing in an issue before you write the code.

## Getting set up

You need [uv](https://docs.astral.sh/uv/). It manages the interpreter and the locked dependency
set, so you do not need to install a Python yourself or make a virtualenv.

```bash
uv sync
```

Then:

```bash
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy              # type-check, in strict mode
```

CI runs exactly these, against the same locked versions, so a green run locally means a green run
there. Tests run on Python 3.10 through 3.14.

If you change a dependency in `pyproject.toml`, commit the resulting `uv.lock` alongside it. CI
syncs with `--locked` and fails if the two disagree.

## What we look for

- **Tests.** The suite mocks HTTP with [respx](https://lundberg.github.io/respx/), so tests are
  fast and hit no network. New behavior needs a test; a bug fix needs one that fails without it.
- **Types.** mypy runs in strict mode over `src`, `tests`, and `examples`.
- **Lenient parsing.** Models tolerate fields they do not recognize and keep the raw body in
  `raw`. An SDK that raises on a response it half-understands ages badly.
- **No new runtime dependencies** without a good reason. httpx is the only one, deliberately.

## The API this wraps

The [Dregs manual](https://dregs.com/manual/api/) is the source of truth for the REST API. If
this SDK disagrees with the manual, the manual wins; please say so in your pull request so both
get fixed.

## Reporting problems

Bugs and feature requests go to
[GitHub issues](https://github.com/dregs-sdk/dregs-sdk-python/issues). Security reports go to
[security@dregs.com](mailto:security@dregs.com) instead — see [SECURITY.md](SECURITY.md).
Questions about your account or the service go to [support@dregs.com](mailto:support@dregs.com).
