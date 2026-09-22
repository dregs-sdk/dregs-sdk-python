"""Client construction, configuration, and the track() request body."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from dregs import Dregs

from .conftest import BASE_URL, SECRET_KEY


class TestConstruction:
    def test_reads_the_secret_key_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DREGS_SECRET_KEY", SECRET_KEY)

        with Dregs() as client:
            assert client.base_url == "https://dregs.com/api"

    def test_reads_the_base_url_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DREGS_BASE_URL", "https://staging.example.com/api")

        with Dregs(SECRET_KEY) as client:
            assert client.base_url == "https://staging.example.com/api"

    def test_a_trailing_slash_on_the_base_url_does_not_double_up(self) -> None:
        with Dregs(SECRET_KEY, base_url=f"{BASE_URL}/") as client:
            assert client.base_url == BASE_URL

    def test_a_missing_key_names_the_environment_variable(self) -> None:
        with pytest.raises(ValueError, match="DREGS_SECRET_KEY"):
            Dregs()

    def test_a_public_key_is_refused_with_an_explanation(self) -> None:
        with pytest.raises(ValueError, match="public key"):
            Dregs("pk_abcdefghQijklmQabcdefghijklmn")

    def test_negative_retries_are_refused(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):
            Dregs(SECRET_KEY, max_retries=-1)


class TestTrackRequest:
    @respx.mock
    def test_sends_the_documented_body(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        client.track(
            "user.signup",
            identity="user_12345",
            data={"plan": "pro"},
            identity_data={"email": "ada@example.com"},
            event_id="signup-991",
        )

        body = json.loads(route.calls.last.request.content)

        assert body["id"] == "signup-991"
        assert body["type"] == "user.signup"
        assert body["data"] == {"plan": "pro"}
        assert body["identity"] == {"id": "user_12345", "data": {"email": "ada@example.com"}}
        assert body["source"] == "python-sdk"

    @respx.mock
    def test_authorizes_with_the_secret_key(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        client.track("user.signup", identity="user_12345")

        request = route.calls.last.request

        assert request.headers["Authorization"] == f"Bearer {SECRET_KEY}"
        assert request.headers["User-Agent"].startswith("dregs-python/")

    @respx.mock
    def test_generates_an_event_id_so_retries_are_idempotent(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        client.track("user.signup", identity="user_12345")
        client.track("user.signup", identity="user_12345")

        first = json.loads(route.calls[0].request.content)["id"]
        second = json.loads(route.calls[1].request.content)["id"]

        assert first and second
        assert first != second
        assert not first.startswith("dregs-")

    @respx.mock
    def test_sends_an_aware_timestamp_as_utc(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        client.track(
            "user.signup",
            identity="user_12345",
            timestamp=datetime(2026, 9, 21, 14, 22, 9, tzinfo=timezone.utc),
        )

        assert json.loads(route.calls.last.request.content)["timestamp"] == "2026-09-21T14:22:09Z"

    @respx.mock
    def test_reads_a_naive_timestamp_as_utc(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        client.track("user.signup", identity="user_12345", timestamp=datetime(2026, 9, 21, 14, 22, 9))

        assert json.loads(route.calls.last.request.content)["timestamp"] == "2026-09-21T14:22:09Z"

    @respx.mock
    def test_omits_the_timestamp_when_the_caller_does(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        client.track("user.signup", identity="user_12345")

        assert "timestamp" not in json.loads(route.calls.last.request.content)

    def test_an_empty_identity_is_refused_before_any_request(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="identity is required"):
            client.track("user.signup", identity="")

    def test_an_empty_event_type_is_refused(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="event_type is required"):
            client.track("", identity="user_12345")

    def test_a_reserved_event_id_is_refused(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="reserved"):
            client.track("user.signup", identity="user_12345", event_id="dregs-1234")

    def test_an_overlong_event_id_is_refused(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="64 characters"):
            client.track("user.signup", identity="user_12345", event_id="x" * 65)


class TestTrackResponse:
    @respx.mock
    def test_reports_an_accepted_event(self, client: Dregs) -> None:
        respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1", "fingerprint": None})
        )

        result = client.track("user.signup", identity="user_12345")

        assert result.accepted is True
        assert result.id == "evt_1"
        assert result.status == "success"

    @respx.mock
    def test_a_quiet_rejection_is_not_accepted(self, client: Dregs) -> None:
        respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": None, "fingerprint": None})
        )

        result = client.track("user.signup", identity="user_12345")

        assert result.accepted is False
        assert result.id is None


class TestBringYourOwnHttpClient:
    @respx.mock
    def test_a_supplied_client_is_used_and_left_open(self) -> None:
        respx.post(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
        )

        http = httpx.Client(headers={"X-Tenant": "acme"})

        with Dregs(SECRET_KEY, base_url=BASE_URL, http_client=http) as client:
            client.track("user.signup", identity="user_12345")

        assert not http.is_closed

        http.close()
