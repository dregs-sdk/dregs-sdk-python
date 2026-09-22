"""The async client behaves exactly as the sync one."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from dregs import AsyncDregs, Category, NotFoundError, QuotaExceededError

from .conftest import BASE_URL, SECRET_KEY


@respx.mock
async def test_track_sends_the_same_body() -> None:
    route = respx.post(f"{BASE_URL}/events").mock(
        return_value=httpx.Response(200, json={"status": "success", "id": "evt_1"})
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        result = await client.track(
            "user.signup",
            identity="user_12345",
            data={"plan": "pro"},
            event_id="signup-991",
        )

    body = json.loads(route.calls.last.request.content)

    assert body["id"] == "signup-991"
    assert body["identity"]["id"] == "user_12345"
    assert result.accepted is True


@respx.mock
async def test_scores_are_parsed() -> None:
    respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(
        return_value=httpx.Response(
            200, json=[{"category": "HUMANITY", "value": 85}, {"category": "BEHAVIOR", "value": 68}]
        )
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        scores = await client.identities.scores("user_12345")

    assert scores.humanity == 85
    assert scores.behavior == 68
    assert [s.category for s in scores] == [Category.HUMANITY, Category.BEHAVIOR]


@respx.mock
async def test_analysis_is_parsed() -> None:
    respx.get(f"{BASE_URL}/identities/user_12345/analysis").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 2000871,
                "identityId": "user_12345",
                "scores": [
                    {
                        "category": "HUMANITY",
                        "value": 85,
                        "observations": [{"category": "HUMANITY", "id": "humanity.user-agent"}],
                    }
                ],
            },
        )
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        analysis = await client.identities.analysis("user_12345")

    assert analysis.id == 2000871
    assert analysis.observations[0].id == "humanity.user-agent"


@respx.mock
async def test_get_and_analyze_reach_their_endpoints() -> None:
    get_route = respx.get(f"{BASE_URL}/identities/user_12345").mock(
        return_value=httpx.Response(200, json={"id": "user_12345"})
    )
    analyze_route = respx.post(f"{BASE_URL}/identities/user_12345/actions/analyze").mock(
        return_value=httpx.Response(201)
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        identity = await client.identities.get("user_12345")

        await client.identities.analyze("user_12345")

    assert identity.id == "user_12345"
    assert get_route.called
    assert analyze_route.called


@respx.mock
async def test_errors_map_the_same_way() -> None:
    respx.get(f"{BASE_URL}/identities/nobody").mock(return_value=httpx.Response(404))

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(NotFoundError):
            await client.identities.get("nobody")


@respx.mock
async def test_a_quota_error_is_raised_from_a_body_status() -> None:
    respx.post(f"{BASE_URL}/events").mock(
        return_value=httpx.Response(200, json={"status": "quota_exceeded", "id": None})
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        with pytest.raises(QuotaExceededError):
            await client.track("user.signup", identity="user_12345")


@respx.mock
async def test_a_server_error_is_retried() -> None:
    route = respx.get(f"{BASE_URL}/identities/user_12345").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"id": "user_12345"})]
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=2) as client:
        identity = await client.identities.get("user_12345")

    assert identity.id == "user_12345"
    assert route.call_count == 2


async def test_the_two_clients_expose_the_same_surface() -> None:
    from dregs import Dregs

    sync_names = {n for n in dir(Dregs) if not n.startswith("_")} - {"close"}
    async_names = {n for n in dir(AsyncDregs) if not n.startswith("_")} - {"aclose"}

    assert sync_names == async_names

    from dregs.resources import AsyncIdentities, Identities

    assert {n for n in dir(Identities) if not n.startswith("_")} == {
        n for n in dir(AsyncIdentities) if not n.startswith("_")
    }
