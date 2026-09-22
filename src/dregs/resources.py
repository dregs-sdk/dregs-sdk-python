"""The ``client.identities`` namespace.

These are thin: they name the endpoint, then hand the response to a model. The transport,
retries, and error mapping all live on the client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .models import Analysis, Identity, Scores

if TYPE_CHECKING:
    from ._client import AsyncDregs, Dregs

__all__ = ["AsyncIdentities", "Identities"]


def _path(identity_id: str, suffix: str = "") -> str:
    if not identity_id:
        raise ValueError("An identity id is required.")

    # Identity ids are the caller's own user ids and routinely contain characters that need
    # escaping (an email address being the common one).
    return f"/identities/{quote(identity_id, safe='')}{suffix}"


class Identities:
    """Read identities and their scores."""

    def __init__(self, client: Dregs) -> None:
        self._client = client

    def get(self, identity_id: str) -> Identity:
        """Returns the identity, with its current scores, badges, and attributes.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        payload = self._client._request("GET", _path(identity_id))

        return Identity.from_api(_as_mapping(payload))

    def scores(self, identity_id: str) -> Scores:
        """Returns the four current category scores.

        This is the cheap read and the one most integrations want. It reports the scores Dregs
        has already computed without triggering any work. For the observations behind them, use
        :meth:`analysis`.

        A category that has not been scored yet is absent, so a brand-new identity comes back
        empty.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        payload = self._client._request("GET", _path(identity_id, "/scores"))

        return Scores.from_api(_as_sequence(payload))

    def analysis(self, identity_id: str) -> Analysis:
        """Returns the most recent analysis cycle, with the observations behind each score.

        Use this when you need to show or log *why* an identity scored the way it did.

        Raises:
            NotFoundError: The identity is unknown, or it has not been analyzed yet.
        """
        payload = self._client._request("GET", _path(identity_id, "/analysis"))

        return Analysis.from_api(_as_mapping(payload))

    def analyze(self, identity_id: str) -> None:
        """Queues a re-analysis of the identity.

        Scoring is asynchronous: this returns as soon as the job is queued, not when it has run.
        Poll :meth:`scores` or watch for a webhook rather than expecting fresh scores on the
        next line.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        self._client._request("POST", _path(identity_id, "/actions/analyze"))


class AsyncIdentities:
    """The async twin of :class:`Identities`."""

    def __init__(self, client: AsyncDregs) -> None:
        self._client = client

    async def get(self, identity_id: str) -> Identity:
        """Returns the identity, with its current scores, badges, and attributes."""
        payload = await self._client._request("GET", _path(identity_id))

        return Identity.from_api(_as_mapping(payload))

    async def scores(self, identity_id: str) -> Scores:
        """Returns the four current category scores."""
        payload = await self._client._request("GET", _path(identity_id, "/scores"))

        return Scores.from_api(_as_sequence(payload))

    async def analysis(self, identity_id: str) -> Analysis:
        """Returns the most recent analysis cycle, with the observations behind each score."""
        payload = await self._client._request("GET", _path(identity_id, "/analysis"))

        return Analysis.from_api(_as_mapping(payload))

    async def analyze(self, identity_id: str) -> None:
        """Queues a re-analysis of the identity."""
        await self._client._request("POST", _path(identity_id, "/actions/analyze"))


def _as_mapping(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _as_sequence(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    return [item for item in payload if isinstance(item, dict)]
