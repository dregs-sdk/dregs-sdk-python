"""Typed views over the Dregs API's responses.

Every model keeps the response it was built from in ``raw``, so a field Dregs adds after this
release is still reachable without waiting for an SDK upgrade. Parsing is deliberately lenient:
a missing field becomes ``None`` rather than an error, because an SDK that refuses to parse a
response it half-understands is worse than one that hands back what it got.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

__all__ = [
    "Analysis",
    "Badge",
    "Category",
    "Identity",
    "Observation",
    "Score",
    "Scores",
    "TrackResult",
]


class Category(str, Enum):
    """The four categories Dregs scores an identity in."""

    HUMANITY = "HUMANITY"
    AUTHENTICITY = "AUTHENTICITY"
    UNIQUENESS = "UNIQUENESS"
    BEHAVIOR = "BEHAVIOR"

    @classmethod
    def _missing_(cls, value: object) -> Category | None:
        # Tolerate a category this SDK release predates rather than raising on an otherwise
        # good response.
        if isinstance(value, str):
            for member in cls:
                if member.value == value.upper():
                    return member

        return None


def _parse_datetime(value: Any) -> datetime | None:
    """Parses an ISO-8601 timestamp, returning None for anything unparseable."""
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_category(value: Any) -> Category | None:
    if not isinstance(value, str):
        return None

    try:
        return Category(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class TrackResult:
    """The outcome of a :meth:`dregs.Dregs.track` call.

    Attributes:
        status: The status Dregs reported, normally ``"success"``.
        id: The event's identifier, either the one you supplied or one Dregs generated. It is
            ``None`` when the event was not recorded.
        fingerprint: The device fingerprint Dregs resolved, for events that carried a device
            signature. Server-side events do not, so this is normally ``None``.
        raw: The response body as received.
    """

    status: str | None
    id: str | None
    fingerprint: str | None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def accepted(self) -> bool:
        """Whether Dregs recorded the event.

        This is ``False`` in the uncommon case where Dregs accepts the request without
        recording an event. A server-side integration holding a valid secret key should not
        normally see it, so it is worth a log line if you do. Ingestion failures that are the
        caller's to act on (a bad request, an unknown key, an exhausted quota, a rate limit)
        raise instead of landing here.
        """
        return self.id is not None

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> TrackResult:
        return cls(
            status=payload.get("status"),
            id=payload.get("id"),
            fingerprint=payload.get("fingerprint"),
            raw=payload,
        )


@dataclass(frozen=True)
class Badge:
    """A label Dregs applied to an identity, from an analyzer or a badge rule."""

    slug: str | None
    name: str | None
    type: str | None
    explanation: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Badge:
        return cls(
            slug=payload.get("slug"),
            name=payload.get("name"),
            type=payload.get("type"),
            explanation=payload.get("explanation"),
            metadata=payload.get("metadata") or {},
            raw=payload,
        )


@dataclass(frozen=True)
class Observation:
    """One analyzer's finding, and the reasoning behind a slice of a score.

    Attributes:
        category: The category the observation contributes to.
        id: The analyzer's identifier, such as ``"humanity.user-agent"``.
        label: A human-readable name for the analyzer.
        explanation: A sentence describing what the analyzer found.
        value: 0.0 for entirely suspicious, 1.0 for entirely legitimate.
        confidence: How sure the analyzer is, from 0.0 to 1.0.
        weight: How heavily this observation counts toward the category score.
        metadata: The counts and details behind the finding.
    """

    category: Category | None
    id: str | None
    label: str | None
    explanation: str | None
    value: float | None
    confidence: float | None
    weight: float | None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Observation:
        return cls(
            category=_parse_category(payload.get("category")),
            id=payload.get("id"),
            label=payload.get("label"),
            explanation=payload.get("explanation"),
            value=payload.get("value"),
            confidence=payload.get("confidence"),
            weight=payload.get("weight"),
            metadata=payload.get("metadata") or {},
            raw=payload,
        )


@dataclass(frozen=True)
class Score:
    """One category's score.

    Attributes:
        category: The category scored.
        value: An integer from 0 (worst) to 100 (best).
        observations: The observations behind the score. This is empty on the result of
            :meth:`~dregs.resources.Identities.scores`, which reports the scores alone; the
            observations come from :meth:`~dregs.resources.Identities.analysis`.
    """

    category: Category | None
    value: int | None
    observations: Sequence[Observation] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Score:
        observations = payload.get("observations") or []

        return cls(
            category=_parse_category(payload.get("category")),
            value=payload.get("value"),
            observations=tuple(Observation.from_api(o) for o in observations),
            raw=payload,
        )


@dataclass(frozen=True)
class Scores(Sequence[Score]):
    """An identity's four category scores.

    Behaves as a sequence of :class:`Score`, and also offers the four categories by name::

        scores = client.identities.scores("user_12345")

        if scores.humanity is not None and scores.humanity < 30:
            hold_for_review()

    A category Dregs has not scored yet is absent from the sequence, and its named accessor
    returns ``None``.
    """

    items: tuple[Score, ...] = ()

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[Score]:
        return iter(self.items)

    def __getitem__(self, index: Any) -> Any:
        return self.items[index]

    def get(self, category: Category) -> Score | None:
        """Returns the score for ``category``, or ``None`` when it has not been scored."""
        for score in self.items:
            if score.category is category:
                return score

        return None

    def _value(self, category: Category) -> int | None:
        score = self.get(category)

        return score.value if score else None

    @property
    def humanity(self) -> int | None:
        """How likely it is that a person, rather than a script, is behind the account."""
        return self._value(Category.HUMANITY)

    @property
    def authenticity(self) -> int | None:
        """How genuine the details on the account look."""
        return self._value(Category.AUTHENTICITY)

    @property
    def uniqueness(self) -> int | None:
        """How distinct the account is from others in the same tenant."""
        return self._value(Category.UNIQUENESS)

    @property
    def behavior(self) -> int | None:
        """How ordinary the account's activity looks."""
        return self._value(Category.BEHAVIOR)

    @classmethod
    def from_api(cls, payload: Sequence[Mapping[str, Any]]) -> Scores:
        return cls(items=tuple(Score.from_api(s) for s in payload))


@dataclass(frozen=True)
class Identity:
    """A user Dregs is tracking, and their current scores.

    ``id`` is your own identifier for the user, the one you pass to :meth:`dregs.Dregs.track`
    and to ``dregs.identify()`` in the browser tracker, not an internal Dregs id.
    """

    id: str | None
    display_name: str | None = None
    display_email: str | None = None
    display_username: str | None = None
    humanity_score: int | None = None
    authenticity_score: int | None = None
    uniqueness_score: int | None = None
    behavior_score: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_tracked_at: datetime | None = None
    last_scored_at: datetime | None = None
    disregarded: bool = False
    badges: Sequence[Badge] = ()
    data: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def scores(self) -> Scores:
        """The identity's scores, as a :class:`Scores` for parity with ``identities.scores()``."""
        pairs = (
            (Category.HUMANITY, self.humanity_score),
            (Category.AUTHENTICITY, self.authenticity_score),
            (Category.UNIQUENESS, self.uniqueness_score),
            (Category.BEHAVIOR, self.behavior_score),
        )

        return Scores(items=tuple(Score(category=c, value=v) for c, v in pairs if v is not None))

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Identity:
        return cls(
            id=payload.get("id"),
            display_name=payload.get("displayName"),
            display_email=payload.get("displayEmail"),
            display_username=payload.get("displayUsername"),
            humanity_score=payload.get("humanityScore"),
            authenticity_score=payload.get("authenticityScore"),
            uniqueness_score=payload.get("uniquenessScore"),
            behavior_score=payload.get("behaviorScore"),
            created_at=_parse_datetime(payload.get("createdAt")),
            updated_at=_parse_datetime(payload.get("updatedAt")),
            last_tracked_at=_parse_datetime(payload.get("lastTrackedAt")),
            last_scored_at=_parse_datetime(payload.get("lastScoredAt")),
            disregarded=bool(payload.get("disregarded")),
            badges=tuple(Badge.from_api(b) for b in payload.get("badges") or []),
            data=payload.get("data") or {},
            raw=payload,
        )


@dataclass(frozen=True)
class Analysis:
    """One analysis cycle: the scores an identity was given, and why.

    Attributes:
        id: The cycle's identifier.
        identity_id: The identity that was analyzed.
        scores: The four category scores, each carrying its observations.
        event_count: How many events the cycle considered.
        device_count: How many devices the cycle considered.
        duration_millis: How long the cycle took.
    """

    id: int | None
    identity_id: str | None
    scores: Scores = field(default_factory=Scores)
    event_count: int | None = None
    device_count: int | None = None
    duration_millis: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def observations(self) -> Sequence[Observation]:
        """Every observation from the cycle, across all four categories."""
        return tuple(o for score in self.scores for o in score.observations)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Analysis:
        return cls(
            id=payload.get("id"),
            identity_id=payload.get("identityId"),
            scores=Scores.from_api(payload.get("scores") or []),
            event_count=payload.get("eventCount"),
            device_count=payload.get("deviceCount"),
            duration_millis=payload.get("durationMillis"),
            started_at=_parse_datetime(payload.get("startedAt")),
            finished_at=_parse_datetime(payload.get("finishedAt")),
            raw=payload,
        )
