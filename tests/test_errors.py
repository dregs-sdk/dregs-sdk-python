"""Status codes map to typed errors, and failed requests are retried."""

from __future__ import annotations

import httpx
import pytest
import respx

from dregs import (
    AuthenticationError,
    BadRequestError,
    Dregs,
    DregsAPIError,
    DregsConnectionError,
    DregsError,
    DregsTimeoutError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
)

from .conftest import BASE_URL


def _error_body(status: int, message: str) -> dict[str, object]:
    return {"timestamp": "2026-09-21T14:22:09Z", "status": status, "error": "Error", "message": message}


class TestStatusMapping:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (400, BadRequestError),
            (401, AuthenticationError),
            (402, QuotaExceededError),
            (403, PermissionDeniedError),
            (404, NotFoundError),
            (429, RateLimitError),
            (500, ServerError),
            (503, ServerError),
        ],
    )
    @respx.mock
    def test_each_status_raises_its_own_error(
        self, client: Dregs, status: int, expected: type[DregsAPIError]
    ) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(
            return_value=httpx.Response(status, json=_error_body(status, "No"))
        )

        with pytest.raises(expected) as caught:
            client.identities.get("user_12345")

        assert caught.value.status_code == status

    @respx.mock
    def test_every_error_is_catchable_as_the_base_class(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(return_value=httpx.Response(404))

        with pytest.raises(DregsError):
            client.identities.get("user_12345")

    @respx.mock
    def test_the_api_message_reaches_the_exception(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(
            return_value=httpx.Response(404, json=_error_body(404, "Not Found"))
        )

        with pytest.raises(NotFoundError) as caught:
            client.identities.get("user_12345")

        assert caught.value.message == "Not Found"
        assert "404" in str(caught.value)

    @respx.mock
    def test_a_request_id_is_carried_through(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(
            return_value=httpx.Response(500, headers={"X-Request-Id": "req_abc"})
        )

        with pytest.raises(ServerError) as caught:
            client.identities.get("user_12345")

        assert caught.value.request_id == "req_abc"
        assert "req_abc" in str(caught.value)

    @respx.mock
    def test_a_non_json_error_still_raises_the_right_class(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(
            return_value=httpx.Response(502, text="<html>gateway</html>")
        )

        with pytest.raises(ServerError) as caught:
            client.identities.get("user_12345")

        assert caught.value.body is None


class TestRateLimits:
    @respx.mock
    def test_retry_after_is_exposed(self, client: Dregs) -> None:
        respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "2"}, json={"status": "rate_limited"})
        )

        with pytest.raises(RateLimitError) as caught:
            client.track("user.signup", identity="user_12345")

        assert caught.value.retry_after == 2.0

    @respx.mock
    def test_a_rate_limit_reported_in_the_body_still_raises(self, client: Dregs) -> None:
        """Older API builds answered the ingestion limit with HTTP 200 and a body status."""
        respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "rate_limited", "id": None})
        )

        with pytest.raises(RateLimitError):
            client.track("user.signup", identity="user_12345")

    @respx.mock
    def test_a_quota_reported_in_the_body_still_raises(self, client: Dregs) -> None:
        respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "quota_exceeded", "id": None})
        )

        with pytest.raises(QuotaExceededError) as caught:
            client.track("user.signup", identity="user_12345")

        assert caught.value.status_code == 402


class TestRetries:
    @respx.mock
    def test_a_server_error_is_retried_and_can_succeed(self, retrying_client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/user_12345").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"id": "user_12345"}),
            ]
        )

        identity = retrying_client.identities.get("user_12345")

        assert identity.id == "user_12345"
        assert route.call_count == 2

    @respx.mock
    def test_retries_stop_at_the_configured_limit(self, retrying_client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/user_12345").mock(return_value=httpx.Response(500))

        with pytest.raises(ServerError):
            retrying_client.identities.get("user_12345")

        assert route.call_count == 3  # the first attempt plus two retries

    @respx.mock
    def test_a_rate_limit_is_retried(self, retrying_client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"status": "success", "id": "evt_1"}),
            ]
        )

        result = retrying_client.track("user.signup", identity="user_12345")

        assert result.accepted is True
        assert route.call_count == 2

    @respx.mock
    def test_a_retried_event_keeps_its_id_so_ingestion_stays_idempotent(self, retrying_client: Dregs) -> None:
        import json as jsonlib

        route = respx.post(f"{BASE_URL}/events").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"status": "success", "id": "evt_1"}),
            ]
        )

        retrying_client.track("user.signup", identity="user_12345")

        first = jsonlib.loads(route.calls[0].request.content)["id"]
        second = jsonlib.loads(route.calls[1].request.content)["id"]

        assert first == second

    @respx.mock
    def test_a_client_error_is_not_retried(self, retrying_client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/user_12345").mock(return_value=httpx.Response(404))

        with pytest.raises(NotFoundError):
            retrying_client.identities.get("user_12345")

        assert route.call_count == 1

    @respx.mock
    def test_a_connection_failure_is_retried_then_raised(self, retrying_client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/user_12345").mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(DregsConnectionError):
            retrying_client.identities.get("user_12345")

        assert route.call_count == 3

    @respx.mock
    def test_a_timeout_raises_its_own_error(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(DregsTimeoutError):
            client.identities.get("user_12345")

    @respx.mock
    def test_a_connection_failure_recovers_when_a_retry_lands(self, retrying_client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(200, json={"id": "user_12345"}),
            ]
        )

        assert retrying_client.identities.get("user_12345").id == "user_12345"
