"""Shared plumbing behind the sync and async clients.

The two clients differ only in how they await httpx. Everything that decides *what* to send,
*how* to read the answer, and *whether* to try again lives here so the two cannot drift.
"""

from __future__ import annotations

import os
import platform
import random
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Final

import httpx

from .errors import (
    DregsAPIError,
    QuotaExceededError,
    RateLimitError,
    error_for_status,
)

DEFAULT_BASE_URL: Final = "https://dregs.com/api"
DEFAULT_TIMEOUT: Final = 10.0
DEFAULT_MAX_RETRIES: Final = 2

SECRET_KEY_ENV: Final = "DREGS_SECRET_KEY"
BASE_URL_ENV: Final = "DREGS_BASE_URL"

#: Statuses worth another attempt. 429 and 5xx are transient by definition; 408 shows up in
#: front of some proxies.
RETRY_STATUSES: Final = frozenset({408, 429, 500, 502, 503, 504})

#: Body-level statuses Dregs uses on ``POST /api/events``.
_STATUS_RATE_LIMITED: Final = "rate_limited"
_STATUS_QUOTA_EXCEEDED: Final = "quota_exceeded"


def _version() -> str:
    from . import __version__

    return __version__


def _user_agent() -> str:
    return f"dregs-python/{_version()} (python {platform.python_version()})"


class BaseClient:
    """Configuration, request construction, and response handling shared by both clients."""

    def __init__(
        self,
        secret_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        resolved_key = secret_key or os.environ.get(SECRET_KEY_ENV)

        if not resolved_key:
            raise ValueError(
                "No Dregs secret key. Pass secret_key=... or set the "
                f"{SECRET_KEY_ENV} environment variable. You will find your credential's secret "
                "key under Settings -> Credentials in the Dregs dashboard."
            )

        if resolved_key.startswith("pk_"):
            raise ValueError(
                "That is a public key. The public key is for the browser tracker and cannot read "
                "identities or scores; this SDK needs the secret key from the same credential, "
                "which starts with 'sk_'."
            )

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        self._secret_key = resolved_key
        self._base_url = (base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def base_url(self) -> str:
        """The API root every request is built against."""
        return self._base_url

    @property
    def max_retries(self) -> int:
        """How many times a failed request is retried before the error is raised."""
        return self._max_retries

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Accept": "application/json",
            "User-Agent": _user_agent(),
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _track_body(
        self,
        event_type: str,
        *,
        identity: str,
        data: Mapping[str, Any] | None,
        identity_data: Mapping[str, Any] | None,
        event_id: str | None,
        timestamp: datetime | None,
        source: str | None,
    ) -> dict[str, Any]:
        """Builds the ``POST /api/events`` body.

        An event id is always sent. When the caller has an id of their own it is used verbatim,
        so reposting the same event is a no-op on the Dregs side; otherwise one is generated,
        which is what makes this client's own retries safe to perform.
        """
        if not event_type:
            raise ValueError("event_type is required.")

        if not identity:
            raise ValueError(
                "identity is required. A server-side event has no device signature, so the "
                "identity is the only thing tying the event to a user."
            )

        resolved_id = event_id if event_id is not None else uuid.uuid4().hex

        if resolved_id.startswith("dregs-"):
            raise ValueError("Event ids starting with 'dregs-' are reserved for Dregs itself.")

        if len(resolved_id) > 64:
            raise ValueError("Event ids cannot be longer than 64 characters.")

        body: dict[str, Any] = {
            "id": resolved_id,
            "type": event_type,
            "data": dict(data or {}),
            "identity": {"id": identity, "data": dict(identity_data or {})},
            "source": source or "python-sdk",
        }

        if timestamp is not None:
            body["timestamp"] = _isoformat(timestamp)

        return body

    def _should_retry(self, *, attempt: int, status_code: int | None) -> bool:
        if attempt >= self._max_retries:
            return False

        return status_code is None or status_code in RETRY_STATUSES

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        """Seconds to wait before attempt ``attempt + 1``.

        ``Retry-After`` wins when the server sent one. Otherwise this is exponential with full
        jitter, which keeps a fleet of workers that all hit the limit at once from retrying in
        lockstep.
        """
        if retry_after is not None and retry_after >= 0:
            return min(retry_after, 60.0)

        return random.uniform(0, min(0.5 * (2**attempt), 8.0))

    def _process(self, response: httpx.Response) -> Any:
        """Turns a response into parsed JSON, or raises the matching error."""
        payload = _json_or_none(response)

        if response.status_code >= 400:
            raise _api_error(response, payload)

        # An older API build reported both of these as HTTP 200 with the outcome in the body.
        # Reading the body as well as the status keeps this SDK correct against either.
        if isinstance(payload, Mapping):
            status = payload.get("status")

            if status == _STATUS_RATE_LIMITED:
                raise RateLimitError(
                    "Ingestion rate limit exceeded for this credential.",
                    body=payload,
                    request_id=_request_id(response),
                    retry_after=_retry_after(response),
                )

            if status == _STATUS_QUOTA_EXCEEDED:
                raise QuotaExceededError(
                    "The account is over its monthly event limit.",
                    status_code=402,
                    body=payload,
                    request_id=_request_id(response),
                )

        return payload


def _isoformat(value: datetime) -> str:
    """Formats a datetime the way the API's Instant parser expects.

    A naive datetime is read as UTC rather than as local time: an event timestamp that silently
    shifted by the server's offset would be worse than one the caller was made to be explicit
    about, but raising on the common ``datetime.utcnow()`` would be hostile.
    """
    moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_or_none(response: httpx.Response) -> Any:
    if not response.content:
        return None

    try:
        return response.json()
    except ValueError:
        return None


def _request_id(response: httpx.Response) -> str | None:
    value = response.headers.get("X-Request-Id")

    return value if isinstance(value, str) else None


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")

    if raw is None:
        return None

    try:
        return float(raw)
    except ValueError:
        # The header also allows an HTTP date, which is rare enough here that falling back to
        # the client's own backoff is better than dragging in a date parser.
        return None


def _api_error(response: httpx.Response, payload: Any) -> DregsAPIError:
    message = _message_from(payload) or response.reason_phrase or "Request failed"
    request_id = _request_id(response)

    if response.status_code == 429:
        return RateLimitError(
            message,
            body=payload,
            request_id=request_id,
            retry_after=_retry_after(response),
        )

    return error_for_status(response.status_code)(
        message,
        status_code=response.status_code,
        body=payload,
        request_id=request_id,
    )


def _message_from(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None

    for key in ("message", "error", "status"):
        value = payload.get(key)

        if isinstance(value, str) and value:
            return value

    return None
