"""Typed views over the Dregs API's responses.

Every model keeps the response it was built from in ``raw``, so a field Dregs adds after this
release is still reachable without waiting for an SDK upgrade. Parsing is deliberately lenient:
a missing field becomes ``None`` rather than an error, because an SDK that refuses to parse a
response it half-understands is worse than one that hands back what it got.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar

__all__ = [
    "Analysis",
    "Badge",
    "Category",
    "Device",
    "Escalation",
    "EscalationSummary",
    "Event",
    "Group",
    "GroupReference",
    "Identity",
    "IdentityReview",
    "LinkedIdentity",
    "Observation",
    "Page",
    "Reference",
    "Score",
    "ScoreHistoryEntry",
    "Scores",
    "TrackResult",
]

T = TypeVar("T")


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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class Page(Sequence[T], Generic[T]):
    """One page of a list call.

    Behaves as a sequence of the items on this page. Pages are numbered from 0. To walk every
    page, use the namespace's ``list_all()`` rather than looping on ``page_number`` yourself.

    Attributes:
        items: The items on this page.
        page_number: This page's number, counting from 0.
        page_size: The most items a page holds.
        total_pages: How many pages there are in all.
        total_elements: How many items there are across every page.
        first: Whether this is the first page.
        last: Whether this is the last page.
    """

    items: tuple[T, ...] = ()
    page_number: int = 0
    page_size: int = 0
    total_pages: int = 0
    total_elements: int = 0
    first: bool = True
    last: bool = True
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __getitem__(self, index: Any) -> Any:
        return self.items[index]

    @property
    def has_next(self) -> bool:
        """Whether another page follows this one."""
        return not self.last and len(self.items) > 0

    @classmethod
    def from_api(cls, payload: Mapping[str, Any], parse: Callable[[Mapping[str, Any]], T]) -> Page[T]:
        items = tuple(parse(item) for item in _mappings(payload.get("content")))

        return cls(
            items=items,
            page_number=payload.get("pageNumber") or 0,
            page_size=payload.get("pageSize") or 0,
            total_pages=payload.get("totalPages") or 0,
            total_elements=payload.get("totalElements") or 0,
            first=payload.get("first", True) is not False,
            last=payload.get("last", True) is not False,
            raw=payload,
        )


@dataclass(frozen=True)
class Reference:
    """A pointer to another resource: its id, a label for display, and its API path."""

    id: str | None
    label: str | None = None
    path: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Reference:
        return cls(id=payload.get("id"), label=payload.get("label"), path=payload.get("path"), raw=payload)


@dataclass(frozen=True)
class GroupReference:
    """A pointer to a group, as it appears on an event."""

    type: str | None
    id: str | None
    label: str | None = None
    path: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> GroupReference:
        return cls(
            type=payload.get("type"),
            id=payload.get("id"),
            label=payload.get("label"),
            path=payload.get("path"),
            raw=payload,
        )


@dataclass(frozen=True)
class Group:
    """An organization, team, workspace, or whatever your application groups users into.

    A group is identified by its ``type`` and ``id`` together, both your own. Dregs normalizes the
    type to lower_snake_case.

    Attributes:
        type: The kind of group, such as ``"organization"`` or ``"team"``.
        id: Your own id for the group.
        display_name: A name for display, taken from the group's attributes.
        identity_count: How many identities are members.
        data: The group's attributes. Empty on the groups of a list call, which leaves them out.
    """

    type: str | None
    id: str | None
    display_name: str | None = None
    identity_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_tracked_at: datetime | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Group:
        return cls(
            type=payload.get("type"),
            id=payload.get("id"),
            display_name=payload.get("displayName"),
            identity_count=payload.get("identityCount"),
            created_at=_parse_datetime(payload.get("createdAt")),
            updated_at=_parse_datetime(payload.get("updatedAt")),
            last_tracked_at=_parse_datetime(payload.get("lastTrackedAt")),
            data=_mapping(payload.get("data")),
            raw=payload,
        )


@dataclass(frozen=True)
class Event:
    """An event Dregs recorded.

    Attributes:
        id: The event's id, either the one you sent or one Dregs generated.
        timestamp: When the event happened.
        identity: The identity the event belongs to, if any.
        groups: The groups the event was sent with.
        fingerprint: The device fingerprint, for events that carried a device signature.
        session: The browser session, for events from the tracker.
        ip: The address the event came from.
        url: The page URL, for events from the tracker.
        source: Where the event came from, such as ``"python-sdk"``.
        name: Your name for the event, such as ``"user.signup"``.
        canonical_type: The Dregs event type your name is mapped to, if it is mapped.
        data: The event's attributes, with sensitive values redacted.
    """

    id: str | None
    timestamp: datetime | None = None
    identity: Reference | None = None
    groups: Sequence[GroupReference] = ()
    fingerprint: str | None = None
    session: str | None = None
    ip: str | None = None
    url: str | None = None
    source: str | None = None
    name: str | None = None
    canonical_type: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Event:
        identity = payload.get("identity")

        return cls(
            id=payload.get("id"),
            timestamp=_parse_datetime(payload.get("timestamp")),
            identity=Reference.from_api(identity) if isinstance(identity, Mapping) else None,
            groups=tuple(GroupReference.from_api(g) for g in _mappings(payload.get("groups"))),
            fingerprint=payload.get("fingerprint"),
            session=payload.get("session"),
            ip=payload.get("ip"),
            url=payload.get("url"),
            source=payload.get("eventSource"),
            name=payload.get("eventName"),
            canonical_type=payload.get("canonicalType"),
            data=_mapping(payload.get("eventData")),
            raw=payload,
        )


@dataclass(frozen=True)
class Device:
    """A browser or device Dregs has seen, identified by its fingerprint."""

    fingerprint: str | None
    ip: str | None = None
    asn: str | None = None
    asn_label: str | None = None
    user_agent: str | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    disregarded: bool = False
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Device:
        return cls(
            fingerprint=payload.get("fingerprint"),
            ip=payload.get("ip"),
            asn=payload.get("asn"),
            asn_label=payload.get("asnLabel"),
            user_agent=payload.get("userAgent"),
            city=payload.get("city"),
            region=payload.get("region"),
            country=payload.get("country"),
            country_code=payload.get("countryCode"),
            timezone=payload.get("timezone"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            disregarded=bool(payload.get("disregarded")),
            first_seen_at=_parse_datetime(payload.get("firstSeenAt")),
            last_seen_at=_parse_datetime(payload.get("lastSeenAt")),
            raw=payload,
        )


@dataclass(frozen=True)
class LinkedIdentity:
    """Another identity Dregs believes is connected to this one, such as by a shared device.

    Attributes:
        identity_id: The linked identity's id.
        display_name: The linked identity's display name.
        type: How they are linked, such as ``"SAME_DEVICE"`` or ``"SHARED_IP"``.
        value: How strongly they are linked, from 0.0 to 1.0.
        confidence: How sure Dregs is of the link, from 0.0 to 1.0.
        explanation: A sentence describing the link.
    """

    identity_id: str | None
    display_name: str | None = None
    type: str | None = None
    value: float | None = None
    confidence: float | None = None
    explanation: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> LinkedIdentity:
        return cls(
            identity_id=payload.get("targetIdentityId"),
            display_name=payload.get("targetDisplayName"),
            type=payload.get("type"),
            value=payload.get("value"),
            confidence=payload.get("confidence"),
            explanation=payload.get("explanation"),
            metadata=_mapping(payload.get("metadata")),
            created_at=_parse_datetime(payload.get("createdAt")),
            raw=payload,
        )


@dataclass(frozen=True)
class ScoreHistoryEntry:
    """The scores one past analysis cycle produced.

    Attributes:
        cycle_id: The cycle's id, which :meth:`~dregs.resources.Identities.analysis` accepts to
            fetch that cycle's observations.
    """

    cycle_id: int | None
    humanity: int | None = None
    authenticity: int | None = None
    uniqueness: int | None = None
    behavior: int | None = None
    event_count: int | None = None
    device_count: int | None = None
    finished_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> ScoreHistoryEntry:
        return cls(
            cycle_id=payload.get("id"),
            humanity=payload.get("humanityScore"),
            authenticity=payload.get("authenticityScore"),
            uniqueness=payload.get("uniquenessScore"),
            behavior=payload.get("behaviorScore"),
            event_count=payload.get("eventCount"),
            device_count=payload.get("deviceCount"),
            finished_at=_parse_datetime(payload.get("finishedAt")),
            raw=payload,
        )


@dataclass(frozen=True)
class IdentityReview:
    """A review of an identity's analysis, written by Dregs's AI reviewer.

    Attributes:
        id: The review's id.
        status: ``"PENDING"`` until the review has run, then ``"FINISHED"`` or ``"FAILED"``.
        feedback: The note you sent with the request, if any.
        summary: The reviewer's findings, once it has run.
    """

    id: int | None
    identity_id: str | None = None
    status: str | None = None
    feedback: str | None = None
    summary: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> IdentityReview:
        return cls(
            id=payload.get("id"),
            identity_id=payload.get("identityId"),
            status=payload.get("status"),
            feedback=payload.get("userFeedback"),
            summary=payload.get("summary"),
            error_message=payload.get("errorMessage"),
            created_at=_parse_datetime(payload.get("createdAt")),
            completed_at=_parse_datetime(payload.get("completedAt")),
            raw=payload,
        )


@dataclass(frozen=True)
class Escalation:
    """An escalation an escalation rule opened against an identity.

    Attributes:
        id: The escalation's id.
        status: ``"OPEN"``, ``"ACKNOWLEDGED"``, or ``"CLOSED"``.
        severity: ``"INFO"``, ``"WARNING"``, or ``"CRITICAL"``.
        identity: The identity the escalation is about.
        rule: The escalation rule that opened it.
        scores: The identity's scores when the escalation opened, by category name.
    """

    id: int | None
    status: str | None = None
    severity: str | None = None
    identity: Reference | None = None
    rule: Reference | None = None
    scores: Mapping[str, Any] = field(default_factory=dict)
    opened_at: datetime | None = None
    acknowledged_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> Escalation:
        identity = payload.get("identity")
        rule = payload.get("escalationRule")

        return cls(
            id=payload.get("id"),
            status=payload.get("status"),
            severity=payload.get("severity"),
            identity=Reference.from_api(identity) if isinstance(identity, Mapping) else None,
            rule=Reference.from_api(rule) if isinstance(rule, Mapping) else None,
            scores=_mapping(payload.get("scoreSnapshot")),
            opened_at=_parse_datetime(payload.get("openedAt")),
            acknowledged_at=_parse_datetime(payload.get("acknowledgedAt")),
            closed_at=_parse_datetime(payload.get("closedAt")),
            created_at=_parse_datetime(payload.get("createdAt")),
            raw=payload,
        )


@dataclass(frozen=True)
class EscalationSummary:
    """How many escalations are in each status."""

    open: int = 0
    acknowledged: int = 0
    closed: int = 0
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> EscalationSummary:
        return cls(
            open=payload.get("open") or 0,
            acknowledged=payload.get("acknowledged") or 0,
            closed=payload.get("closed") or 0,
            raw=payload,
        )
