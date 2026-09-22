"""The sync and async Dregs clients."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from datetime import datetime
from types import TracebackType
from typing import Any

import httpx

from ._base import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, BaseClient
from .errors import DregsAPIError, DregsConnectionError, DregsTimeoutError, RateLimitError
from .models import TrackResult
from .resources import AsyncIdentities, Identities

__all__ = ["AsyncDregs", "Dregs"]


class Dregs(BaseClient):
    """A synchronous Dregs client.

    The secret key comes from the ``DREGS_SECRET_KEY`` environment variable unless you pass one.
    Find it under **Settings -> Credentials** in the dashboard; it is the key starting ``sk_``,
    not the ``pk_`` public key the browser tracker uses.

    ::

        from dregs import Dregs

        with Dregs() as client:
            client.track("user.signup", identity="user_12345", data={"plan": "pro"})

            scores = client.identities.scores("user_12345")

    The client holds a connection pool, so build one and keep it rather than making a new one
    per request. It is safe to share across threads.

    Args:
        secret_key: Your credential's secret key. Defaults to ``$DREGS_SECRET_KEY``.
        base_url: The API root. Defaults to ``$DREGS_BASE_URL``, then ``https://dregs.com/api``.
        timeout: Seconds before a request is abandoned, or an ``httpx.Timeout``.
        max_retries: How many times to retry a failed request. Retries cover connection
            failures, timeouts, 429s, and 5xx, with exponential backoff and jitter; the
            ``Retry-After`` header wins when the server sends one.
        http_client: An ``httpx.Client`` to use instead of the one this client would build,
            for callers who need their own proxies, TLS settings, or transport.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(secret_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)

        self.identities = Identities(self)
        """Read identities, their scores, and their analysis."""

    def track(
        self,
        event_type: str,
        *,
        identity: str,
        data: Mapping[str, Any] | None = None,
        identity_data: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> TrackResult:
        """Records a backend event against an identity.

        ::

            client.track(
                "user.signup",
                identity="user_12345",
                data={"plan": "pro", "referrer": "partner-x"},
                identity_data={"email": "ada@example.com", "name": "Ada Lovelace"},
            )

        Args:
            event_type: Your name for the event, such as ``"user.signup"``. Map it to one of
                Dregs's canonical types under **Settings -> Mappings** so the analyzers know
                what it means.
            identity: Your own id for the user. This is the same id you pass to
                ``dregs.identify()`` in the browser tracker, and the one you look scores up by.
                It is required: a server-side event carries no device signature, so the
                identity is the only thing tying it to a user.
            data: Attributes of the event itself.
            identity_data: Attributes of the *user*, such as email, name, or username. Dregs
                merges these into the identity, and the analyzers lean on them heavily, so send
                them whenever you have them. Flat keys work best; name them as your application
                already does and map them under **Settings -> Mappings**.
            event_id: Your own id for the event, which makes ingestion idempotent: reposting
                the same id returns the original event instead of recording a second one. Pass
                the id your application already has (the row id of the record that triggered
                the event, say). When you omit it the SDK generates one, which is what makes
                its own retries safe. At most 64 characters, and it cannot start with
                ``dregs-``.
            timestamp: When the event happened, if not now. A naive datetime is read as UTC.
            source: A label for where the event came from. Defaults to ``"python-sdk"``.

        Returns:
            A :class:`~dregs.models.TrackResult`. Check ``.accepted`` to confirm Dregs recorded
            the event.

        Raises:
            QuotaExceededError: The account is over its monthly event limit.
            RateLimitError: The credential is ingesting too fast.
            AuthenticationError: The secret key was not recognized.
            BadRequestError: The event was malformed.
        """
        body = self._track_body(
            event_type,
            identity=identity,
            data=data,
            identity_data=identity_data,
            event_id=event_id,
            timestamp=timestamp,
            source=source,
        )

        payload = self._request("POST", "/events", json=body)

        return TrackResult.from_api(payload if isinstance(payload, dict) else {})

    def _request(self, method: str, path: str, *, json: Any = None) -> Any:
        url = self._url(path)
        headers = self._headers()
        attempt = 0

        while True:
            try:
                response = self._http.request(method, url, json=json, headers=headers)
            except httpx.TimeoutException as exc:
                if not self._should_retry(attempt=attempt, status_code=None):
                    raise DregsTimeoutError(f"Request to {url} timed out.") from exc
            except httpx.HTTPError as exc:
                if not self._should_retry(attempt=attempt, status_code=None):
                    raise DregsConnectionError(f"Could not reach Dregs at {url}: {exc}") from exc
            else:
                try:
                    return self._process(response)
                except DregsAPIError as exc:
                    if not self._should_retry(attempt=attempt, status_code=exc.status_code):
                        raise

                    time.sleep(self._backoff(attempt, _retry_after_of(exc)))
                    attempt += 1

                    continue

            time.sleep(self._backoff(attempt, None))
            attempt += 1

    def close(self) -> None:
        """Closes the connection pool, unless you supplied your own ``http_client``."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> Dregs:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncDregs(BaseClient):
    """An asynchronous Dregs client.

    Identical to :class:`Dregs` in every respect but the awaiting::

        from dregs import AsyncDregs

        async with AsyncDregs() as client:
            await client.track("user.signup", identity="user_12345")

            scores = await client.identities.scores("user_12345")
    """

    def __init__(
        self,
        secret_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(secret_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

        self.identities = AsyncIdentities(self)
        """Read identities, their scores, and their analysis."""

    async def track(
        self,
        event_type: str,
        *,
        identity: str,
        data: Mapping[str, Any] | None = None,
        identity_data: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        timestamp: datetime | None = None,
        source: str | None = None,
    ) -> TrackResult:
        """Records a backend event against an identity. See :meth:`Dregs.track`."""
        body = self._track_body(
            event_type,
            identity=identity,
            data=data,
            identity_data=identity_data,
            event_id=event_id,
            timestamp=timestamp,
            source=source,
        )

        payload = await self._request("POST", "/events", json=body)

        return TrackResult.from_api(payload if isinstance(payload, dict) else {})

    async def _request(self, method: str, path: str, *, json: Any = None) -> Any:
        url = self._url(path)
        headers = self._headers()
        attempt = 0

        while True:
            try:
                response = await self._http.request(method, url, json=json, headers=headers)
            except httpx.TimeoutException as exc:
                if not self._should_retry(attempt=attempt, status_code=None):
                    raise DregsTimeoutError(f"Request to {url} timed out.") from exc
            except httpx.HTTPError as exc:
                if not self._should_retry(attempt=attempt, status_code=None):
                    raise DregsConnectionError(f"Could not reach Dregs at {url}: {exc}") from exc
            else:
                try:
                    return self._process(response)
                except DregsAPIError as exc:
                    if not self._should_retry(attempt=attempt, status_code=exc.status_code):
                        raise

                    await asyncio.sleep(self._backoff(attempt, _retry_after_of(exc)))
                    attempt += 1

                    continue

            await asyncio.sleep(self._backoff(attempt, None))
            attempt += 1

    async def aclose(self) -> None:
        """Closes the connection pool, unless you supplied your own ``http_client``."""
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncDregs:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()


def _retry_after_of(exc: DregsAPIError) -> float | None:
    return exc.retry_after if isinstance(exc, RateLimitError) else None
