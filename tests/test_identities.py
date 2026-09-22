"""The identities namespace and the models it returns."""

from __future__ import annotations

import httpx
import respx

from dregs import Category, Dregs

from .conftest import BASE_URL

IDENTITY = {
    "id": "user_12345",
    "displayName": "Ada Lovelace",
    "displayEmail": "ada@example.com",
    "displayUsername": "ada",
    "humanityScore": 85,
    "authenticityScore": 72,
    "uniquenessScore": 91,
    "behaviorScore": 68,
    "createdAt": "2026-09-01T10:00:00Z",
    "lastTrackedAt": "2026-09-21T14:20:00Z",
    "disregarded": False,
    "badges": [{"slug": "behavior.account-takeover-signal", "name": "Account Takeover Suspected"}],
    "data": {"email": "ada@example.com", "plan": "pro"},
}

ANALYSIS = {
    "id": 2000871,
    "identityId": "user_12345",
    "scores": [
        {
            "category": "HUMANITY",
            "value": 85,
            "observations": [
                {
                    "category": "HUMANITY",
                    "id": "humanity.user-agent",
                    "label": "User Agent Analysis",
                    "explanation": "Browser fingerprint consistent with standard Chrome on macOS",
                    "value": 0.92,
                    "confidence": 0.85,
                    "weight": 0.85,
                    "metadata": {"browser": "Chrome"},
                }
            ],
        },
        {"category": "BEHAVIOR", "value": 68, "observations": []},
    ],
    "eventCount": 47,
    "deviceCount": 2,
    "durationMillis": 312,
    "startedAt": "2026-09-21T14:22:09Z",
    "finishedAt": "2026-09-21T14:22:09Z",
}


class TestGet:
    @respx.mock
    def test_parses_an_identity(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(return_value=httpx.Response(200, json=IDENTITY))

        identity = client.identities.get("user_12345")

        assert identity.id == "user_12345"
        assert identity.display_email == "ada@example.com"
        assert identity.humanity_score == 85
        assert identity.disregarded is False
        assert identity.data["plan"] == "pro"
        assert identity.created_at is not None
        assert identity.created_at.year == 2026

    @respx.mock
    def test_parses_badges(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(return_value=httpx.Response(200, json=IDENTITY))

        identity = client.identities.get("user_12345")

        assert len(identity.badges) == 1
        assert identity.badges[0].name == "Account Takeover Suspected"

    @respx.mock
    def test_exposes_the_same_scores_view_as_the_scores_call(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(return_value=httpx.Response(200, json=IDENTITY))

        identity = client.identities.get("user_12345")

        assert identity.scores.humanity == 85
        assert identity.scores.behavior == 68

    @respx.mock
    def test_escapes_an_identity_id_that_needs_it(self, client: Dregs) -> None:
        route = respx.get(f"{BASE_URL}/identities/ada%40example.com").mock(
            return_value=httpx.Response(200, json={"id": "ada@example.com"})
        )

        client.identities.get("ada@example.com")

        assert route.called


class TestScores:
    @respx.mock
    def test_exposes_each_category_by_name(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"category": "HUMANITY", "value": 85},
                    {"category": "AUTHENTICITY", "value": 72},
                    {"category": "UNIQUENESS", "value": 91},
                    {"category": "BEHAVIOR", "value": 68},
                ],
            )
        )

        scores = client.identities.scores("user_12345")

        assert scores.humanity == 85
        assert scores.authenticity == 72
        assert scores.uniqueness == 91
        assert scores.behavior == 68

    @respx.mock
    def test_behaves_as_a_sequence(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(
            return_value=httpx.Response(
                200, json=[{"category": "HUMANITY", "value": 85}, {"category": "BEHAVIOR", "value": 68}]
            )
        )

        scores = client.identities.scores("user_12345")

        assert len(scores) == 2
        assert [s.category for s in scores] == [Category.HUMANITY, Category.BEHAVIOR]
        assert scores[0].value == 85

    @respx.mock
    def test_an_unscored_category_reads_as_none(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(
            return_value=httpx.Response(200, json=[{"category": "HUMANITY", "value": 85}])
        )

        scores = client.identities.scores("user_12345")

        assert scores.humanity == 85
        assert scores.behavior is None
        assert scores.get(Category.BEHAVIOR) is None

    @respx.mock
    def test_an_identity_with_no_scores_yet_is_empty(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(return_value=httpx.Response(200, json=[]))

        scores = client.identities.scores("user_12345")

        assert len(scores) == 0
        assert scores.humanity is None

    @respx.mock
    def test_carries_no_observations(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(
            return_value=httpx.Response(200, json=[{"category": "HUMANITY", "value": 85}])
        )

        scores = client.identities.scores("user_12345")

        assert scores[0].observations == ()


class TestAnalysis:
    @respx.mock
    def test_parses_a_cycle_and_its_observations(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/analysis").mock(
            return_value=httpx.Response(200, json=ANALYSIS)
        )

        analysis = client.identities.analysis("user_12345")

        assert analysis.id == 2000871
        assert analysis.identity_id == "user_12345"
        assert analysis.event_count == 47
        assert analysis.scores.humanity == 85

        observation = analysis.scores[0].observations[0]

        assert observation.id == "humanity.user-agent"
        assert observation.label == "User Agent Analysis"
        assert observation.value == 0.92
        assert observation.metadata["browser"] == "Chrome"

    @respx.mock
    def test_flattens_observations_across_categories(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/analysis").mock(
            return_value=httpx.Response(200, json=ANALYSIS)
        )

        analysis = client.identities.analysis("user_12345")

        assert len(analysis.observations) == 1
        assert analysis.observations[0].category is Category.HUMANITY


class TestAnalyze:
    @respx.mock
    def test_posts_to_the_action_endpoint(self, client: Dregs) -> None:
        route = respx.post(f"{BASE_URL}/identities/user_12345/actions/analyze").mock(
            return_value=httpx.Response(201)
        )

        client.identities.analyze("user_12345")

        assert route.called


class TestForwardCompatibility:
    @respx.mock
    def test_an_unknown_field_survives_on_raw(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345").mock(
            return_value=httpx.Response(200, json={"id": "user_12345", "somethingNew": 42})
        )

        identity = client.identities.get("user_12345")

        assert identity.raw["somethingNew"] == 42

    @respx.mock
    def test_an_unknown_category_does_not_break_parsing(self, client: Dregs) -> None:
        respx.get(f"{BASE_URL}/identities/user_12345/scores").mock(
            return_value=httpx.Response(
                200, json=[{"category": "REPUTATION", "value": 50}, {"category": "HUMANITY", "value": 85}]
            )
        )

        scores = client.identities.scores("user_12345")

        assert len(scores) == 2
        assert scores.humanity == 85
        assert scores[0].category is None
        assert scores[0].raw["category"] == "REPUTATION"
