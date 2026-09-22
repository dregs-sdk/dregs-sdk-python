"""Verifying webhooks Dregs sends you.

Dregs signs every webhook with the channel's signing secret: ``X-Dregs-Signature`` is the
hex-encoded HMAC-SHA256 of the raw request body. Verify it before you act on the payload,
and verify it against the bytes you received rather than a re-serialized dict, because
re-serializing changes key order and whitespace and will not match.

::

    from dregs.webhooks import verify

    @app.post("/webhooks/dregs")
    def receive(request):
        event = verify(
            payload=request.body,
            signature=request.headers["X-Dregs-Signature"],
            secret=os.environ["DREGS_WEBHOOK_SECRET"],
        )

        handle(event)

The signing secret is shown once, when you create the webhook channel. It is not your API
secret key: one authenticates you to Dregs, the other proves a payload came from Dregs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Final

from .errors import WebhookVerificationError

__all__ = ["DEFAULT_TOLERANCE_SECONDS", "compute_signature", "verify", "verify_signature"]

SIGNATURE_HEADER: Final = "X-Dregs-Signature"
TIMESTAMP_HEADER: Final = "X-Dregs-Timestamp"
EVENT_HEADER: Final = "X-Dregs-Event"

#: How far out of date a webhook's timestamp may be before :func:`verify` rejects it.
DEFAULT_TOLERANCE_SECONDS: Final = 300


def compute_signature(payload: bytes | str, secret: str) -> str:
    """Returns the hex-encoded HMAC-SHA256 of ``payload`` under ``secret``."""
    body = payload.encode("utf-8") if isinstance(payload, str) else payload

    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes | str, signature: str, secret: str) -> bool:
    """Returns whether ``signature`` matches ``payload``.

    The comparison is constant-time. Prefer :func:`verify`, which also rejects replays and
    hands back the parsed event; reach for this one only when you need the boolean.
    """
    if not signature or not secret:
        return False

    return hmac.compare_digest(compute_signature(payload, secret), signature.strip())


def verify(
    payload: bytes | str,
    signature: str,
    secret: str,
    *,
    tolerance: float | None = DEFAULT_TOLERANCE_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verifies a webhook and returns its parsed body.

    Args:
        payload: The raw request body, exactly as received. Not a parsed dict.
        signature: The ``X-Dregs-Signature`` header.
        secret: The channel's signing secret.
        tolerance: How many seconds out of date the payload's own ``timestamp`` may be before
            it is treated as a replay. Pass ``None`` to skip the check, which you should only
            do if you are deduplicating on the event id yourself. The timestamp is inside the
            signed body, so an attacker cannot alter it without breaking the signature.
        now: The current time, for tests.

    Returns:
        The parsed webhook body: ``event``, ``timestamp``, and the payload for that event.

    Raises:
        WebhookVerificationError: The signature did not match, the body was not JSON, or the
            payload is older than ``tolerance``.
    """
    if not verify_signature(payload, signature, secret):
        raise WebhookVerificationError(
            "The webhook signature did not match. Check that you are verifying the raw request "
            "body rather than a re-serialized copy, and that the signing secret belongs to the "
            "channel that sent this delivery."
        )

    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise WebhookVerificationError(f"The webhook body was not valid JSON: {exc}") from exc

    if not isinstance(event, dict):
        raise WebhookVerificationError("The webhook body was not a JSON object.")

    if tolerance is not None:
        _check_freshness(event, tolerance=tolerance, now=now)

    return event


def _check_freshness(event: Mapping[str, Any], *, tolerance: float, now: datetime | None) -> None:
    raw = event.get("timestamp")

    if not isinstance(raw, str) or not raw:
        raise WebhookVerificationError(
            "The webhook carried no timestamp, so it cannot be checked for replay. Pass "
            "tolerance=None if you are deduplicating deliveries some other way."
        )

    try:
        sent = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WebhookVerificationError(f"The webhook timestamp was unreadable: {raw!r}") from exc

    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)

    reference = now or datetime.now(timezone.utc)

    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    age = abs((reference - sent).total_seconds())

    if age > tolerance:
        raise WebhookVerificationError(
            f"The webhook timestamp is {age:.0f}s away from now, beyond the {tolerance:.0f}s "
            "tolerance. Treating it as a replay."
        )
