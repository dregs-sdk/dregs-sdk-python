# Dregs Python SDK

[![PyPI](https://img.shields.io/pypi/v/dregs.svg)](https://pypi.org/project/dregs/)
[![Python](https://img.shields.io/pypi/pyversions/dregs.svg)](https://pypi.org/project/dregs/)
[![License](https://img.shields.io/pypi/l/dregs.svg)](LICENSE)

The official Python client for [Dregs](https://dregs.com), which scores the users of your application
for fraud and abuse across four categories: humanity, authenticity, uniqueness, and behavior.

Send events from your backend, read back the scores and the observations behind them.

```bash
pip install dregs
```

## Getting started

You need the **secret key** from an API credential, which you will find under **Settings → Credentials**
in the Dregs dashboard. It starts with `sk_`. The `pk_` public key is for the browser tracker and cannot
read identities or scores.

```python
import os

from dregs import Dregs

client = Dregs(os.environ["DREGS_SECRET_KEY"])
```

The key is read from `DREGS_SECRET_KEY` when you do not pass one, so `Dregs()` on its own is usually
enough. The client holds a connection pool: build one at startup and keep it, rather than making a new
one per request. It is safe to share across threads.

## Tracking events

```python
client.track(
    "user.signup",
    identity="user_12345",
    data={"plan": "pro", "referrer": "partner-x"},
    identity_data={"email": "ada@example.com", "name": "Ada Lovelace"},
)
```

`identity` is your own id for the user — the same one you pass to `dregs.identify()` in the browser
tracker, and the one you look scores up by. It is required: a server-side event carries no device
signature, so the identity is the only thing tying the event to a user.

`identity_data` carries attributes of the *user* rather than the event. The analyzers lean on these
heavily, so send them whenever you have them. Name the keys the way your application already does and
map them to Dregs's canonical fields under **Settings → Mappings**; the same goes for event names.

### Idempotency

Every event is sent with an `id`, which makes ingestion idempotent: reposting the same id returns the
original event instead of recording a second one. Pass the id your application already has, and a retry
after a timeout can never double-count.

```python
client.track("purchase", identity="user_12345", event_id=f"order-{order.id}")
```

When you omit it the SDK generates one, which is what makes its own retries safe.

### What comes back

```python
result = client.track("user.signup", identity="user_12345")

result.accepted  # True when Dregs recorded the event
result.id  # the event's id
```

`accepted` is `False` in the uncommon case where Dregs accepts the request without recording an
event. Failures that are yours to act on raise instead — see [Errors](#errors).

## Reading scores

```python
scores = client.identities.scores("user_12345")

scores.humanity  # 85
scores.authenticity  # 72
scores.uniqueness  # 91
scores.behavior  # 68
```

This is the cheap read and the one most integrations want. A category Dregs has not scored yet reads as
`None`, and a brand-new identity comes back empty. `Scores` is also a sequence, so you can iterate it.

Scoring is **asynchronous**. Scores appear moments after the events that move them, not in the same
breath, so read them at a decision point rather than immediately after a `track()` call.

```python
if scores.authenticity is not None and scores.authenticity < 40:
    hold_for_review("user_12345")
```

### Seeing exactly why

The scores are the summary; the observations are the evidence. When you need to show or log *why* an
identity scored the way it did, ask for the analysis.

```python
analysis = client.identities.analysis("user_12345")

for observation in analysis.observations:
    print(f"{observation.label}: {observation.explanation} (value {observation.value})")
```

Each observation carries the analyzer that produced it, a `value` from 0.0 (suspicious) to 1.0
(legitimate), a `confidence`, a `weight`, and the counts behind the finding in `metadata`. `analysis()`
raises `NotFoundError` until the identity has been analyzed at least once.

### The whole identity

```python
identity = client.identities.get("user_12345")

identity.display_email  # "ada@example.com"
identity.humanity_score  # 85
identity.badges  # (Badge(name="Account Takeover Suspected", ...),)
identity.data  # every attribute you have sent
```

### Forcing a rescore

```python
client.identities.analyze("user_12345")
```

This queues the work and returns; it does not wait for the cycle to finish. Dregs rescores on its own
as events arrive, so you rarely need this outside of a support or backfill flow.

## Errors

```python
from dregs import QuotaExceededError, RateLimitError, NotFoundError, DregsError

try:
    client.track("user.signup", identity="user_12345")
except QuotaExceededError:
    ...  # over the monthly event limit; the event was not queued
except RateLimitError as exc:
    ...  # ingesting too fast; exc.retry_after when the server said how long
except DregsError:
    ...  # anything else this library raises
```

| Exception | When |
| --- | --- |
| `BadRequestError` | 400, the event was malformed |
| `AuthenticationError` | 401, the secret key was not recognized |
| `QuotaExceededError` | 402, the account is over its monthly event limit |
| `PermissionDeniedError` | 403, the credential may not do this |
| `NotFoundError` | 404, no such identity, or it has not been analyzed |
| `RateLimitError` | 429, too many requests |
| `ServerError` | 5xx |
| `DregsTimeoutError` | the request timed out |
| `DregsConnectionError` | the request never reached Dregs |

All of them derive from `DregsError`. Those that reached the API also carry `status_code`, `body`, and
`request_id`.

### Retries

Connection failures, timeouts, 429s, and 5xx are retried automatically with exponential backoff and
jitter, honouring `Retry-After` when the server sends one. Two retries by default:

```python
client = Dregs(max_retries=5)  # or 0 to handle it yourself
```

## Async

Every method has an async twin with the same signature.

```python
from dregs import AsyncDregs

async with AsyncDregs() as client:
    await client.track("user.signup", identity="user_12345")

    scores = await client.identities.scores("user_12345")
```

## Webhooks

Dregs signs every webhook with the channel's signing secret. Verify it against the **raw request body**
before acting on the payload — a re-serialized dict will not match, because key order and whitespace
change.

```python
from dregs.webhooks import verify
from dregs import WebhookVerificationError


@app.post("/webhooks/dregs")
def receive(request):
    try:
        event = verify(
            payload=request.body,
            signature=request.headers["X-Dregs-Signature"],
            secret=os.environ["DREGS_WEBHOOK_SECRET"],
        )
    except WebhookVerificationError:
        return Response(status=400)

    handle(event)
```

`verify` also rejects payloads older than five minutes as replays; pass `tolerance=None` to skip that if
you are deduplicating on the event id yourself. The signing secret is shown once, when you create the
webhook channel, and is not your API secret key.

## Configuration

```python
client = Dregs(
    secret_key=None,  # defaults to $DREGS_SECRET_KEY
    base_url=None,  # defaults to $DREGS_BASE_URL, then https://dregs.com/api
    timeout=10.0,  # seconds, or an httpx.Timeout
    max_retries=2,
    http_client=None,  # bring your own httpx.Client for proxies or custom TLS
)
```

## Type checking

The package ships type hints and a `py.typed` marker, so mypy and pyright see the full surface with no
stubs. Responses are plain frozen dataclasses; each one also keeps the body it was built from in `raw`,
so a field Dregs adds after this release is reachable without waiting for an SDK upgrade.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy
```

[uv](https://docs.astral.sh/uv/) manages the interpreter and the locked dependencies, so the same
commands produce the same environment locally and in CI.

## Links

- [Dregs manual](https://dregs.com/manual/) and [REST API reference](https://dregs.com/manual/api/)
- [Dregs MCP server](https://github.com/dregs-sdk/dregs-mcp), for connecting AI agents to your data
- [Security policy](SECURITY.md)

## License

MIT. See [LICENSE](LICENSE).
