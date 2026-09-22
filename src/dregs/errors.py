"""Exceptions raised by the Dregs SDK.

Every error raised by this library derives from :class:`DregsError`, so a caller that only
wants a coarse "the Dregs call failed" branch can catch that one class. Errors that came back
from the API carry the HTTP status and the parsed body; errors that never reached the API
(connection refused, DNS failure, timeout) derive from :class:`DregsConnectionError` instead.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AuthenticationError",
    "BadRequestError",
    "DregsAPIError",
    "DregsConnectionError",
    "DregsError",
    "DregsTimeoutError",
    "NotFoundError",
    "PermissionDeniedError",
    "QuotaExceededError",
    "RateLimitError",
    "ServerError",
    "WebhookVerificationError",
]


class DregsError(Exception):
    """Base class for everything this library raises."""


class DregsConnectionError(DregsError):
    """The request never reached Dregs: DNS, TCP, TLS, or a dropped connection."""


class DregsTimeoutError(DregsConnectionError):
    """The request was still outstanding when the configured timeout elapsed."""


class WebhookVerificationError(DregsError):
    """An incoming webhook did not verify against the channel's signing secret."""


class DregsAPIError(DregsError):
    """Dregs answered, and the answer was an error.

    Attributes:
        status_code: The HTTP status code.
        message: The human-readable message, taken from the response body when it carries one.
        body: The parsed JSON body, or ``None`` when the response was not JSON.
        request_id: Value of the ``X-Request-Id`` response header, when present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.status_code = status_code
        self.body = body
        self.request_id = request_id

    def __str__(self) -> str:
        suffix = f" (request {self.request_id})" if self.request_id else ""

        return f"HTTP {self.status_code}: {self.message}{suffix}"


class BadRequestError(DregsAPIError):
    """400. The request was malformed or missing something Dregs requires.

    For event ingestion this most often means the event carried neither an identity nor a
    device, or the body failed validation.
    """


class AuthenticationError(DregsAPIError):
    """401. The secret key was missing, unrecognized, revoked, or expired."""


class QuotaExceededError(DregsAPIError):
    """402. The account is over its monthly event limit and ingestion is refused.

    Events are not queued while an account is over its limit, so the caller decides whether to
    drop the event or hold it. The limit resets with the billing period; upgrading the plan
    clears it immediately.
    """


class PermissionDeniedError(DregsAPIError):
    """403. The credential authenticated but is not allowed to do this."""


class NotFoundError(DregsAPIError):
    """404. No such identity, or no analysis has been run for it yet."""


class RateLimitError(DregsAPIError):
    """429. The credential exceeded its request rate limit.

    Attributes:
        retry_after: Seconds to wait before retrying, from the ``Retry-After`` header when the
            response carried one.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        body: Any = None,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body, request_id=request_id)

        self.retry_after = retry_after


class ServerError(DregsAPIError):
    """5xx. Something went wrong inside Dregs. These are retried automatically."""


_STATUS_ERRORS: dict[int, type[DregsAPIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: QuotaExceededError,
    403: PermissionDeniedError,
    404: NotFoundError,
    429: RateLimitError,
}


def error_for_status(status_code: int) -> type[DregsAPIError]:
    """Returns the exception class that represents ``status_code``."""
    if status_code in _STATUS_ERRORS:
        return _STATUS_ERRORS[status_code]

    if status_code >= 500:
        return ServerError

    return DregsAPIError
