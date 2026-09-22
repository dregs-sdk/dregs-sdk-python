"""Dregs: fraud and abuse scoring for the users of your application.

Send events from your backend, read back the scores and the observations behind them::

    from dregs import Dregs

    with Dregs() as client:
        client.track(
            "user.signup",
            identity="user_12345",
            data={"plan": "pro"},
            identity_data={"email": "ada@example.com"},
        )

        scores = client.identities.scores("user_12345")

        if scores.authenticity is not None and scores.authenticity < 40:
            hold_for_review("user_12345")

Scoring is asynchronous, so scores appear moments after the events that move them rather than
in the same breath. See https://dregs.com/manual/api/ for the API this wraps.
"""

from __future__ import annotations

__version__ = "0.1.0"

from ._client import AsyncDregs, Dregs
from .errors import (
    AuthenticationError,
    BadRequestError,
    DregsAPIError,
    DregsConnectionError,
    DregsError,
    DregsTimeoutError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
    WebhookVerificationError,
)
from .models import (
    Analysis,
    Badge,
    Category,
    Identity,
    Observation,
    Score,
    Scores,
    TrackResult,
)

__all__ = [
    "Analysis",
    "AsyncDregs",
    "AuthenticationError",
    "BadRequestError",
    "Badge",
    "Category",
    "Dregs",
    "DregsAPIError",
    "DregsConnectionError",
    "DregsError",
    "DregsTimeoutError",
    "Identity",
    "NotFoundError",
    "Observation",
    "PermissionDeniedError",
    "QuotaExceededError",
    "RateLimitError",
    "Score",
    "Scores",
    "ServerError",
    "TrackResult",
    "WebhookVerificationError",
    "__version__",
]
