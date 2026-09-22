# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-22

The first release. A server-side client for tracking events and reading scores.

### Added

- `Dregs` and `AsyncDregs` clients, authenticating with a credential's `sk_` secret key against a
  configurable base URL.
- `track()` for recording backend events against an identity, always sending an idempotency `id`
  so a retry cannot double-count.
- `identities.get()`, `identities.scores()`, `identities.analysis()`, and `identities.analyze()`.
- Typed errors for 400, 401, 402, 403, 404, 429, and 5xx, plus connection and timeout failures,
  all deriving from `DregsError`.
- Automatic retries with exponential backoff and jitter, honouring `Retry-After`.
- `dregs.webhooks.verify()` for checking a webhook's signature and rejecting replays.
- Typed models with a `raw` escape hatch, and a `py.typed` marker.

[Unreleased]: https://github.com/dregs-sdk/dregs-sdk-python/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dregs-sdk/dregs-sdk-python/releases/tag/v0.1.0
