"""The groups, events, devices, and escalations namespaces, the rest of identities, and paging."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from dregs import AsyncDregs, Dregs

from .conftest import BASE_URL, SECRET_KEY


def page(
    content: list[dict[str, object]], *, number: int = 0, last: bool = True, total: int | None = None
) -> dict[str, object]:
    return {
        "pageNumber": number,
        "pageSize": 2,
        "totalPages": number + 1 if last else number + 2,
        "totalElements": total if total is not None else len(content),
        "content": content,
        "first": number == 0,
        "last": last,
        "numberOfElements": len(content),
    }


GROUP = {
    "type": "organization",
    "id": "org_678",
    "displayName": "Acme Inc",
    "identityCount": 12,
    "createdAt": "2026-10-01T10:00:00Z",
    "lastTrackedAt": "2026-10-15T10:00:00Z",
    "data": {"name": "Acme Inc", "plan": "enterprise"},
}


class TestPaging:
    @respx.mock
    def test_sends_page_and_filters_and_drops_unset_ones(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities").mock(return_value=httpx.Response(200, json=page([])))

        client.identities.list(term="ada", page=2, page_size=50, sort="humanityScore", order="asc")

        params = route.calls.last.request.url.params

        assert params["term"] == "ada"
        assert params["pageNumber"] == "2"
        assert params["pageSize"] == "50"
        assert params["sort"] == "humanityScore"
        assert params["order"] == "ASC"
        assert "group" not in params
        assert "badge" not in params

    @respx.mock
    def test_a_page_is_a_sequence_with_its_position(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities").mock(
            return_value=httpx.Response(200, json=page([{"id": "a"}, {"id": "b"}], last=False, total=5))
        )

        result = client.identities.list()

        assert [i.id for i in result] == ["a", "b"]
        assert len(result) == 2
        assert result.total_elements == 5
        assert result.has_next is True

    @respx.mock
    def test_list_all_walks_every_page(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/groups").mock(
            side_effect=[
                httpx.Response(
                    200, json=page([{"type": "team", "id": "1"}, {"type": "team", "id": "2"}], last=False)
                ),
                httpx.Response(200, json=page([{"type": "team", "id": "3"}], number=1, last=True)),
            ]
        )

        ids = [g.id for g in client.groups.list_all(group_type="team")]

        assert ids == ["1", "2", "3"]
        assert [c.request.url.params["pageNumber"] for c in route.calls] == ["0", "1"]
        assert all(c.request.url.params["type"] == "team" for c in route.calls)

    @respx.mock
    def test_list_all_stops_on_an_empty_page_even_if_not_marked_last(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/events").mock(
            return_value=httpx.Response(200, json=page([], last=False))
        )

        assert list(client.events.list_all()) == []
        assert route.call_count == 1

    def test_refuses_a_negative_page(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="from 0"):
            client.devices.list(page=-1)

    def test_refuses_an_unknown_order(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="asc"):
            client.escalations.list(order="sideways")


class TestIdentities:
    @respx.mock
    def test_analysis_of_a_past_cycle(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/user_12345/analysis/2000871").mock(
            return_value=httpx.Response(200, json={"id": 2000871, "identityId": "user_12345", "scores": []})
        )

        analysis = client.identities.analysis("user_12345", 2000871)

        assert route.called
        assert analysis.id == 2000871

    @respx.mock
    def test_history(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/user_12345/history").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": 9,
                        "humanityScore": 80,
                        "behaviorScore": 60,
                        "eventCount": 3,
                        "finishedAt": "2026-10-01T00:00:00Z",
                    }
                ],
            )
        )

        history = client.identities.history("user_12345", limit=10)

        assert route.calls.last.request.url.params["limit"] == "10"
        assert history[0].cycle_id == 9
        assert history[0].humanity == 80
        assert history[0].authenticity is None
        assert history[0].finished_at is not None

    @respx.mock
    def test_links(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/links").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": 1,
                        "targetIdentityId": "user_999",
                        "targetDisplayName": "Bob",
                        "type": "SAME_DEVICE",
                        "value": 0.9,
                        "confidence": 0.8,
                    }
                ],
            )
        )

        links = client.identities.links("user_12345")

        assert links[0].identity_id == "user_999"
        assert links[0].type == "SAME_DEVICE"

    @respx.mock
    def test_update_sends_only_what_was_given(self, client: Dregs) -> None:
        route = respx.patch(f"{BASE_URL}/identities/user_12345").mock(
            return_value=httpx.Response(200, json={"id": "user_12345", "disregarded": True})
        )

        identity = client.identities.update("user_12345", disregarded=True)

        assert json.loads(route.calls.last.request.content) == {"disregarded": True}
        assert identity.disregarded is True

    def test_update_with_nothing_is_refused(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="disregarded"):
            client.identities.update("user_12345")

    @respx.mock
    def test_review_and_reviews(self, client: Dregs) -> None:
        post = respx.post(f"{BASE_URL}/identities/user_12345/actions/review").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 7,
                    "identityId": "user_12345",
                    "status": "PENDING",
                    "userFeedback": "real customer",
                },
            )
        )
        respx.get(f"{BASE_URL}/identities/user_12345/reviews").mock(
            return_value=httpx.Response(200, json=[{"id": 7, "status": "FINISHED", "summary": "Looks fine."}])
        )

        review = client.identities.review("user_12345", feedback="real customer")
        reviews = client.identities.reviews("user_12345")

        assert json.loads(post.calls.last.request.content) == {"feedback": "real customer"}
        assert review.status == "PENDING"
        assert review.feedback == "real customer"
        assert reviews[0].summary == "Looks fine."


class TestGroups:
    @respx.mock
    def test_get(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/groups/organization/org_678").mock(
            return_value=httpx.Response(200, json=GROUP)
        )

        group = client.groups.get("organization", "org_678")

        assert group.display_name == "Acme Inc"
        assert group.identity_count == 12
        assert group.data["plan"] == "enterprise"
        assert group.created_at is not None

    @respx.mock
    def test_create_defaults_the_type_and_sends_attributes(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/groups").mock(return_value=httpx.Response(201, json=GROUP))

        client.groups.create("org_678", attributes={"name": "Acme Inc"})

        assert json.loads(route.calls.last.request.content) == {
            "type": "organization",
            "id": "org_678",
            "attributes": {"name": "Acme Inc"},
        }

    @respx.mock
    def test_create_with_no_attributes_sends_an_empty_object(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/groups").mock(return_value=httpx.Response(201, json=GROUP))

        client.groups.create("team_42", group_type="team")

        assert json.loads(route.calls.last.request.content)["attributes"] == {}

    @respx.mock
    def test_update(self, client: Dregs) -> None:
        route = respx.patch(f"{BASE_URL}/groups/team/team_42").mock(
            return_value=httpx.Response(200, json=GROUP)
        )

        client.groups.update("team", "team_42", {"name": "Payments"})

        assert json.loads(route.calls.last.request.content) == {"attributes": {"name": "Payments"}}

    @respx.mock
    def test_membership(self, client: Dregs) -> None:
        put = respx.put(f"{BASE_URL}/groups/team/team_42/identities/ada%40example.com").mock(
            return_value=httpx.Response(204)
        )
        delete = respx.delete(f"{BASE_URL}/groups/team/team_42/identities/ada%40example.com").mock(
            return_value=httpx.Response(204)
        )

        assert client.groups.add_member("team", "team_42", "ada@example.com") is None
        assert client.groups.remove_member("team", "team_42", "ada@example.com") is None
        assert put.called and delete.called

    def test_a_missing_id_is_refused_before_any_request(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="group id"):
            client.groups.get("team", "")


class TestEvents:
    @respx.mock
    def test_get_parses_groups_and_identity(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/events/signup-991").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "signup-991",
                    "timestamp": "2026-10-15T10:00:00Z",
                    "identity": {"id": "user_12345", "label": "Ada", "path": "/api/identities/user_12345"},
                    "groups": [
                        {
                            "type": "team",
                            "id": "team_42",
                            "label": "Payments",
                            "path": "/api/groups/team/team_42",
                        }
                    ],
                    "eventSource": "python-sdk",
                    "eventName": "user.signup",
                    "canonicalType": "SIGNUP",
                    "eventData": {"plan": "pro"},
                },
            )
        )

        event = client.events.get("signup-991")

        assert event.name == "user.signup"
        assert event.canonical_type == "SIGNUP"
        assert event.identity is not None and event.identity.id == "user_12345"
        assert event.groups[0].type == "team"
        assert event.data["plan"] == "pro"

    @respx.mock
    def test_list_filters(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/events").mock(return_value=httpx.Response(200, json=page([])))

        client.events.list(identity="user_12345", group="team_42", group_type="team")

        params = route.calls.last.request.url.params

        assert params["identity"] == "user_12345"
        assert params["group"] == "team_42"
        assert params["groupType"] == "team"


class TestDevices:
    @respx.mock
    def test_update(self, client: Dregs) -> None:
        route = respx.patch(f"{BASE_URL}/devices/abc123").mock(
            return_value=httpx.Response(
                200, json={"fingerprint": "abc123", "disregarded": True, "countryCode": "US"}
            )
        )

        device = client.devices.update("abc123", disregarded=True)

        assert json.loads(route.calls.last.request.content) == {"disregarded": True}
        assert device.disregarded is True
        assert device.country_code == "US"


class TestEscalations:
    @respx.mock
    def test_list_upper_cases_status_and_severity(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/escalations").mock(return_value=httpx.Response(200, json=page([])))

        client.escalations.list(status="open", severity="critical")

        params = route.calls.last.request.url.params

        assert params["status"] == "OPEN"
        assert params["severity"] == "CRITICAL"

    @respx.mock
    def test_update(self, client: Dregs) -> None:
        route = respx.patch(f"{BASE_URL}/escalations/41").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 41,
                    "status": "ACKNOWLEDGED",
                    "severity": "WARNING",
                    "identity": {"id": "user_12345"},
                    "escalationRule": {"id": "3", "label": "Low humanity"},
                    "scoreSnapshot": {"humanity": 12},
                },
            )
        )

        escalation = client.escalations.update(41, status="acknowledged")

        assert json.loads(route.calls.last.request.content) == {"status": "ACKNOWLEDGED"}
        assert escalation.rule is not None and escalation.rule.label == "Low humanity"
        assert escalation.scores["humanity"] == 12

    def test_update_refuses_an_unknown_status(self, client: Dregs) -> None:
        with pytest.raises(ValueError, match="acknowledged"):
            client.escalations.update(41, status="snoozed")

    @respx.mock
    def test_summary(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/escalations/summary").mock(
            return_value=httpx.Response(200, json={"open": 3, "acknowledged": 1, "closed": 20})
        )

        summary = client.escalations.summary()

        assert (summary.open, summary.acknowledged, summary.closed) == (3, 1, 20)


@respx.mock
async def test_async_list_all_walks_every_page() -> None:
    respx.get(f"{BASE_URL}/devices").mock(
        side_effect=[
            httpx.Response(200, json=page([{"fingerprint": "a"}], last=False)),
            httpx.Response(200, json=page([{"fingerprint": "b"}], number=1)),
        ]
    )

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        fingerprints = [d.fingerprint async for d in client.devices.list_all()]

    assert fingerprints == ["a", "b"]


@respx.mock
async def test_async_groups_create() -> None:
    route = respx.post(f"{BASE_URL}/groups").mock(return_value=httpx.Response(201, json=GROUP))

    async with AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as client:
        group = await client.groups.create("org_678", attributes={"name": "Acme Inc"})

    assert route.called
    assert group.id == "org_678"
