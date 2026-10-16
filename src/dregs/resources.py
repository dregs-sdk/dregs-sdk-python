"""The ``client.identities``, ``client.groups``, ``client.events``, ``client.devices``, and
``client.escalations`` namespaces.

These are thin: each method names the endpoint, then hands the response to a model. The transport,
retries, and error mapping all live on the client. Every call is described once, as a
:class:`_Call`, and the sync and async namespaces both run that description, so the two cannot
drift.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from urllib.parse import quote

from ._base import DEFAULT_GROUP_TYPE
from .models import (
    Analysis,
    Device,
    Escalation,
    EscalationSummary,
    Event,
    Group,
    Identity,
    IdentityReview,
    LinkedIdentity,
    Page,
    ScoreHistoryEntry,
    Scores,
)

if TYPE_CHECKING:
    from ._client import AsyncDregs, Dregs

__all__ = [
    "AsyncDevices",
    "AsyncEscalations",
    "AsyncEvents",
    "AsyncGroups",
    "AsyncIdentities",
    "Devices",
    "Escalations",
    "Events",
    "Groups",
    "Identities",
]

T = TypeVar("T")


@dataclass(frozen=True)
class _Call(Generic[T]):
    method: str
    path: str
    parse: Callable[[Any], T]
    params: Mapping[str, Any] | None = None
    json: Any = None


@dataclass(frozen=True)
class _ListCall(Generic[T]):
    path: str
    parse: Callable[[Mapping[str, Any]], T]
    filters: Mapping[str, Any] = field(default_factory=dict)
    page_size: int | None = None
    sort: str | None = None
    order: str | None = None

    def page(self, number: int) -> _Call[Page[T]]:
        params = {
            **self.filters,
            "pageNumber": number,
            "pageSize": self.page_size,
            "sort": self.sort,
            "order": _order(self.order),
        }

        return _Call("GET", self.path, lambda p: Page.from_api(_as_mapping(p), self.parse), params)


def _segment(value: str, what: str) -> str:
    if value is None or str(value) == "":
        raise ValueError(f"{what} is required.")

    # Ids are the caller's own and routinely contain characters that need escaping (an email
    # address being the common one).
    return quote(str(value), safe="")


def _identity_path(identity_id: str, suffix: str = "") -> str:
    return f"/identities/{_segment(identity_id, 'An identity id')}{suffix}"


def _group_path(group_type: str, group_id: str, suffix: str = "") -> str:
    return f"/groups/{_segment(group_type, 'A group type')}/{_segment(group_id, 'A group id')}{suffix}"


def _order(order: str | None) -> str | None:
    if order is None:
        return None

    if order.lower() not in ("asc", "desc"):
        raise ValueError("order is 'asc' or 'desc'.")

    return order.upper()


def _page_number(page: int) -> int:
    if page < 0:
        raise ValueError("Pages are numbered from 0.")

    return page


def _attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    if attributes is not None and not isinstance(attributes, Mapping):
        raise ValueError("attributes must be a mapping, such as {'name': 'Acme Inc'}.")

    return dict(attributes or {})


def _nothing(_: Any) -> None:
    return None


class _Runner:
    """Runs a :class:`_Call` on a sync client."""

    def __init__(self, client: Dregs) -> None:
        self._client = client

    def _run(self, call: _Call[T]) -> T:
        payload = self._client._request(call.method, call.path, json=call.json, params=call.params)

        return call.parse(payload)

    def _walk(self, call: _ListCall[T]) -> Iterator[T]:
        number = 0

        while True:
            page = self._run(call.page(number))

            yield from page

            if not page.has_next:
                return

            number += 1


class _AsyncRunner:
    """Runs a :class:`_Call` on an async client."""

    def __init__(self, client: AsyncDregs) -> None:
        self._client = client

    async def _run(self, call: _Call[T]) -> T:
        payload = await self._client._request(call.method, call.path, json=call.json, params=call.params)

        return call.parse(payload)

    async def _walk(self, call: _ListCall[T]) -> AsyncIterator[T]:
        number = 0

        while True:
            page = await self._run(call.page(number))

            for item in page:
                yield item

            if not page.has_next:
                return

            number += 1


# Identities ---------------------------------------------------------------------------------


def _identities_list(
    *,
    term: str | None,
    group: str | None,
    group_type: str | None,
    device: str | None,
    badge: str | None,
    page_size: int | None,
    sort: str | None,
    order: str | None,
) -> _ListCall[Identity]:
    filters = {"term": term, "group": group, "groupType": group_type, "device": device, "badge": badge}

    return _ListCall("/identities", Identity.from_api, filters, page_size, sort, order)


def _identities_get(identity_id: str) -> _Call[Identity]:
    return _Call("GET", _identity_path(identity_id), lambda p: Identity.from_api(_as_mapping(p)))


def _identities_scores(identity_id: str) -> _Call[Scores]:
    return _Call("GET", _identity_path(identity_id, "/scores"), lambda p: Scores.from_api(_as_sequence(p)))


def _identities_analysis(identity_id: str, cycle_id: int | None) -> _Call[Analysis]:
    suffix = "/analysis" if cycle_id is None else f"/analysis/{_segment(str(cycle_id), 'A cycle id')}"

    return _Call("GET", _identity_path(identity_id, suffix), lambda p: Analysis.from_api(_as_mapping(p)))


def _identities_history(identity_id: str, limit: int | None) -> _Call[list[ScoreHistoryEntry]]:
    return _Call(
        "GET",
        _identity_path(identity_id, "/history"),
        lambda p: [ScoreHistoryEntry.from_api(e) for e in _as_sequence(p)],
        {"limit": limit},
    )


def _identities_links(identity_id: str) -> _Call[list[LinkedIdentity]]:
    return _Call(
        "GET",
        _identity_path(identity_id, "/links"),
        lambda p: [LinkedIdentity.from_api(e) for e in _as_sequence(p)],
    )


def _identities_reviews(identity_id: str) -> _Call[list[IdentityReview]]:
    return _Call(
        "GET",
        _identity_path(identity_id, "/reviews"),
        lambda p: [IdentityReview.from_api(e) for e in _as_sequence(p)],
    )


def _identities_review(identity_id: str, feedback: str | None) -> _Call[IdentityReview]:
    return _Call(
        "POST",
        _identity_path(identity_id, "/actions/review"),
        lambda p: IdentityReview.from_api(_as_mapping(p)),
        json={"feedback": feedback} if feedback else {},
    )


def _identities_analyze(identity_id: str) -> _Call[None]:
    return _Call("POST", _identity_path(identity_id, "/actions/analyze"), _nothing)


def _identities_update(
    identity_id: str, *, disregarded: bool | None, attributes: Mapping[str, Any] | None
) -> _Call[Identity]:
    body: dict[str, Any] = {}

    if disregarded is not None:
        body["disregarded"] = bool(disregarded)

    if attributes is not None:
        body["attributes"] = _attributes(attributes)

    if not body:
        raise ValueError("Pass disregarded, attributes, or both.")

    return _Call("PATCH", _identity_path(identity_id), lambda p: Identity.from_api(_as_mapping(p)), json=body)


class Identities(_Runner):
    """Read identities, their scores, and their analysis."""

    def list(
        self,
        *,
        term: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        badge: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Identity]:
        """Returns one page of identities, most recently updated first.

        Args:
            term: Free text matched against ids, names, emails, and usernames.
            group: Only members of the group with this id. Pair it with ``group_type`` when
                your group ids are not unique across types.
            group_type: Only members of groups of this type.
            device: Only identities seen on the device with this fingerprint.
            badge: Only identities carrying the badge with this slug.
            page: The page to return, counting from 0.
            page_size: Items per page, at most 100.
            sort: The field to sort on, such as ``"lastTrackedAt"`` or ``"humanityScore"``.
            order: ``"asc"`` or ``"desc"``.

        Use :meth:`list_all` to walk every page.
        """
        call = _identities_list(
            term=term,
            group=group,
            group_type=group_type,
            device=device,
            badge=badge,
            page_size=page_size,
            sort=sort,
            order=order,
        )

        return self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        term: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        badge: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Iterator[Identity]:
        """Yields every identity that matches, fetching pages as it goes. See :meth:`list`."""
        return self._walk(
            _identities_list(
                term=term,
                group=group,
                group_type=group_type,
                device=device,
                badge=badge,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    def get(self, identity_id: str) -> Identity:
        """Returns the identity, with its current scores, badges, and attributes.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        return self._run(_identities_get(identity_id))

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
        return self._run(_identities_scores(identity_id))

    def analysis(self, identity_id: str, cycle_id: int | None = None) -> Analysis:
        """Returns an analysis cycle, with the observations behind each score.

        Use this when you need to show or log *why* an identity scored the way it did.

        Args:
            identity_id: The identity.
            cycle_id: A past cycle to return, from :meth:`history`. The most recent cycle when
                omitted.

        Raises:
            NotFoundError: The identity is unknown, or it has not been analyzed yet.
        """
        return self._run(_identities_analysis(identity_id, cycle_id))

    def history(self, identity_id: str, *, limit: int | None = None) -> Sequence[ScoreHistoryEntry]:
        """Returns the scores of past analysis cycles, newest first.

        Args:
            identity_id: The identity.
            limit: The most cycles to return. The API's default is 100.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        return self._run(_identities_history(identity_id, limit))

    def links(self, identity_id: str) -> Sequence[LinkedIdentity]:
        """Returns the other identities Dregs believes are connected to this one.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        return self._run(_identities_links(identity_id))

    def analyze(self, identity_id: str) -> None:
        """Queues a re-analysis of the identity.

        Scoring is asynchronous: this returns as soon as the job is queued, not when it has run.
        Poll :meth:`scores` or watch for a webhook rather than expecting fresh scores on the
        next line.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        self._run(_identities_analyze(identity_id))

    def update(
        self,
        identity_id: str,
        *,
        disregarded: bool | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Identity:
        """Updates an identity and returns it.

        Args:
            identity_id: The identity.
            disregarded: ``True`` to leave the identity out of scoring and escalations, such as
                for your own staff or test accounts. Linked identities are re-scored.
            attributes: Attributes to merge into the identity, as ``identity_data`` on
                :meth:`~dregs.Dregs.track` would.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        return self._run(_identities_update(identity_id, disregarded=disregarded, attributes=attributes))

    def reviews(self, identity_id: str) -> Sequence[IdentityReview]:
        """Returns the AI reviews requested for this identity, newest first.

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        return self._run(_identities_reviews(identity_id))

    def review(self, identity_id: str, *, feedback: str | None = None) -> IdentityReview:
        """Asks Dregs's AI reviewer to look over the identity's analysis.

        The review runs in the background, so the result comes back ``PENDING``. Read it again
        with :meth:`reviews` once it has finished.

        Args:
            identity_id: The identity.
            feedback: What you think the analysis got wrong, such as "this is a real customer".

        Raises:
            NotFoundError: Dregs has never seen this identity.
        """
        return self._run(_identities_review(identity_id, feedback))


class AsyncIdentities(_AsyncRunner):
    """The async twin of :class:`Identities`."""

    async def list(
        self,
        *,
        term: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        badge: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Identity]:
        """Returns one page of identities. See :meth:`Identities.list`."""
        call = _identities_list(
            term=term,
            group=group,
            group_type=group_type,
            device=device,
            badge=badge,
            page_size=page_size,
            sort=sort,
            order=order,
        )

        return await self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        term: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        badge: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> AsyncIterator[Identity]:
        """Yields every identity that matches. Use with ``async for``."""
        return self._walk(
            _identities_list(
                term=term,
                group=group,
                group_type=group_type,
                device=device,
                badge=badge,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    async def get(self, identity_id: str) -> Identity:
        """Returns the identity, with its current scores, badges, and attributes."""
        return await self._run(_identities_get(identity_id))

    async def scores(self, identity_id: str) -> Scores:
        """Returns the four current category scores."""
        return await self._run(_identities_scores(identity_id))

    async def analysis(self, identity_id: str, cycle_id: int | None = None) -> Analysis:
        """Returns an analysis cycle, with the observations behind each score."""
        return await self._run(_identities_analysis(identity_id, cycle_id))

    async def history(self, identity_id: str, *, limit: int | None = None) -> Sequence[ScoreHistoryEntry]:
        """Returns the scores of past analysis cycles, newest first."""
        return await self._run(_identities_history(identity_id, limit))

    async def links(self, identity_id: str) -> Sequence[LinkedIdentity]:
        """Returns the other identities Dregs believes are connected to this one."""
        return await self._run(_identities_links(identity_id))

    async def analyze(self, identity_id: str) -> None:
        """Queues a re-analysis of the identity."""
        await self._run(_identities_analyze(identity_id))

    async def update(
        self,
        identity_id: str,
        *,
        disregarded: bool | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Identity:
        """Updates an identity and returns it. See :meth:`Identities.update`."""
        return await self._run(
            _identities_update(identity_id, disregarded=disregarded, attributes=attributes)
        )

    async def reviews(self, identity_id: str) -> Sequence[IdentityReview]:
        """Returns the AI reviews requested for this identity, newest first."""
        return await self._run(_identities_reviews(identity_id))

    async def review(self, identity_id: str, *, feedback: str | None = None) -> IdentityReview:
        """Asks Dregs's AI reviewer to look over the identity's analysis."""
        return await self._run(_identities_review(identity_id, feedback))


# Groups -------------------------------------------------------------------------------------


def _groups_list(
    *,
    group_type: str | None,
    identity: str | None,
    term: str | None,
    page_size: int | None,
    sort: str | None,
    order: str | None,
) -> _ListCall[Group]:
    return _ListCall(
        "/groups",
        Group.from_api,
        {"type": group_type, "identity": identity, "term": term},
        page_size,
        sort,
        order,
    )


def _groups_get(group_type: str, group_id: str) -> _Call[Group]:
    return _Call("GET", _group_path(group_type, group_id), lambda p: Group.from_api(_as_mapping(p)))


def _groups_create(
    group_id: str, group_type: str | None, attributes: Mapping[str, Any] | None
) -> _Call[Group]:
    _segment(group_id, "A group id")

    body = {
        "type": group_type or DEFAULT_GROUP_TYPE,
        "id": str(group_id),
        "attributes": _attributes(attributes),
    }

    return _Call("POST", "/groups", lambda p: Group.from_api(_as_mapping(p)), json=body)


def _groups_update(group_type: str, group_id: str, attributes: Mapping[str, Any]) -> _Call[Group]:
    return _Call(
        "PATCH",
        _group_path(group_type, group_id),
        lambda p: Group.from_api(_as_mapping(p)),
        json={"attributes": _attributes(attributes)},
    )


def _groups_member(method: str, group_type: str, group_id: str, identity_id: str) -> _Call[None]:
    suffix = f"/identities/{_segment(identity_id, 'An identity id')}"

    return _Call(method, _group_path(group_type, group_id, suffix), _nothing)


class Groups(_Runner):
    """Read and manage groups: the organizations, teams, or workspaces your users belong to.

    :meth:`~dregs.Dregs.track` already records groups and memberships as events arrive. These
    calls are for reading them back, and for keeping Dregs in step when something changes outside
    an event, such as a user leaving a team.
    """

    def list(
        self,
        *,
        group_type: str | None = None,
        identity: str | None = None,
        term: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Group]:
        """Returns one page of groups, most recently active first.

        Args:
            group_type: Only groups of this type, such as ``"team"``.
            identity: Only groups this identity belongs to.
            term: Free text matched against group ids and names.
            page: The page to return, counting from 0.
            page_size: Items per page, at most 100.
            sort: The field to sort on, such as ``"displayName"`` or ``"lastTrackedAt"``.
            order: ``"asc"`` or ``"desc"``.

        The groups in a list leave out their attributes; :meth:`get` returns them.
        """
        call = _groups_list(
            group_type=group_type, identity=identity, term=term, page_size=page_size, sort=sort, order=order
        )

        return self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        group_type: str | None = None,
        identity: str | None = None,
        term: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Iterator[Group]:
        """Yields every group that matches, fetching pages as it goes. See :meth:`list`."""
        return self._walk(
            _groups_list(
                group_type=group_type,
                identity=identity,
                term=term,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    def get(self, group_type: str, group_id: str) -> Group:
        """Returns the group, with its attributes.

        Raises:
            NotFoundError: No group of this type has this id.
        """
        return self._run(_groups_get(group_type, group_id))

    def create(
        self,
        group_id: str,
        *,
        group_type: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Group:
        """Creates a group, or merges ``attributes`` into the group that already has this type and id.

        Args:
            group_id: Your own id for the group.
            group_type: The kind of group. ``"organization"`` when omitted.
            attributes: Attributes such as a name or plan.
        """
        return self._run(_groups_create(group_id, group_type, attributes))

    def update(self, group_type: str, group_id: str, attributes: Mapping[str, Any]) -> Group:
        """Merges ``attributes`` into the group and returns it.

        Raises:
            NotFoundError: No group of this type has this id.
        """
        return self._run(_groups_update(group_type, group_id, attributes))

    def add_member(self, group_type: str, group_id: str, identity_id: str) -> None:
        """Makes the identity a member of the group. Adding an existing member does nothing.

        Raises:
            NotFoundError: The group or the identity is unknown.
        """
        self._run(_groups_member("PUT", group_type, group_id, identity_id))

    def remove_member(self, group_type: str, group_id: str, identity_id: str) -> None:
        """Removes the identity from the group, such as when a user leaves a team.

        Raises:
            NotFoundError: The group or the identity is unknown.
        """
        self._run(_groups_member("DELETE", group_type, group_id, identity_id))


class AsyncGroups(_AsyncRunner):
    """The async twin of :class:`Groups`."""

    async def list(
        self,
        *,
        group_type: str | None = None,
        identity: str | None = None,
        term: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Group]:
        """Returns one page of groups. See :meth:`Groups.list`."""
        call = _groups_list(
            group_type=group_type, identity=identity, term=term, page_size=page_size, sort=sort, order=order
        )

        return await self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        group_type: str | None = None,
        identity: str | None = None,
        term: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> AsyncIterator[Group]:
        """Yields every group that matches. Use with ``async for``."""
        return self._walk(
            _groups_list(
                group_type=group_type,
                identity=identity,
                term=term,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    async def get(self, group_type: str, group_id: str) -> Group:
        """Returns the group, with its attributes."""
        return await self._run(_groups_get(group_type, group_id))

    async def create(
        self,
        group_id: str,
        *,
        group_type: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Group:
        """Creates a group, or merges attributes into the existing one. See :meth:`Groups.create`."""
        return await self._run(_groups_create(group_id, group_type, attributes))

    async def update(self, group_type: str, group_id: str, attributes: Mapping[str, Any]) -> Group:
        """Merges ``attributes`` into the group and returns it."""
        return await self._run(_groups_update(group_type, group_id, attributes))

    async def add_member(self, group_type: str, group_id: str, identity_id: str) -> None:
        """Makes the identity a member of the group."""
        await self._run(_groups_member("PUT", group_type, group_id, identity_id))

    async def remove_member(self, group_type: str, group_id: str, identity_id: str) -> None:
        """Removes the identity from the group."""
        await self._run(_groups_member("DELETE", group_type, group_id, identity_id))


# Events -------------------------------------------------------------------------------------


def _events_list(
    *,
    identity: str | None,
    group: str | None,
    group_type: str | None,
    device: str | None,
    session: str | None,
    term: str | None,
    page_size: int | None,
    sort: str | None,
    order: str | None,
) -> _ListCall[Event]:
    filters = {
        "identity": identity,
        "group": group,
        "groupType": group_type,
        "device": device,
        "session": session,
        "term": term,
    }

    return _ListCall("/events", Event.from_api, filters, page_size, sort, order)


def _events_get(event_id: str) -> _Call[Event]:
    return _Call(
        "GET", f"/events/{_segment(event_id, 'An event id')}", lambda p: Event.from_api(_as_mapping(p))
    )


class Events(_Runner):
    """Read the events Dregs has recorded. To record one, use :meth:`~dregs.Dregs.track`."""

    def list(
        self,
        *,
        identity: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        session: str | None = None,
        term: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Event]:
        """Returns one page of events, newest first.

        Args:
            identity: Only events from this identity.
            group: Only events sent with the group with this id.
            group_type: Only events sent with a group of this type.
            device: Only events from the device with this fingerprint.
            session: Only events from this browser session.
            term: Free text matched against event names and data.
            page: The page to return, counting from 0.
            page_size: Items per page, at most 100.
            sort: The field to sort on, such as ``"timestamp"`` or ``"eventName"``.
            order: ``"asc"`` or ``"desc"``.
        """
        call = _events_list(
            identity=identity,
            group=group,
            group_type=group_type,
            device=device,
            session=session,
            term=term,
            page_size=page_size,
            sort=sort,
            order=order,
        )

        return self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        identity: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        session: str | None = None,
        term: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Iterator[Event]:
        """Yields every event that matches, fetching pages as it goes. See :meth:`list`."""
        return self._walk(
            _events_list(
                identity=identity,
                group=group,
                group_type=group_type,
                device=device,
                session=session,
                term=term,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    def get(self, event_id: str) -> Event:
        """Returns the event with this id.

        Raises:
            NotFoundError: No event has this id.
        """
        return self._run(_events_get(event_id))


class AsyncEvents(_AsyncRunner):
    """The async twin of :class:`Events`."""

    async def list(
        self,
        *,
        identity: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        session: str | None = None,
        term: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Event]:
        """Returns one page of events, newest first. See :meth:`Events.list`."""
        call = _events_list(
            identity=identity,
            group=group,
            group_type=group_type,
            device=device,
            session=session,
            term=term,
            page_size=page_size,
            sort=sort,
            order=order,
        )

        return await self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        identity: str | None = None,
        group: str | None = None,
        group_type: str | None = None,
        device: str | None = None,
        session: str | None = None,
        term: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> AsyncIterator[Event]:
        """Yields every event that matches. Use with ``async for``."""
        return self._walk(
            _events_list(
                identity=identity,
                group=group,
                group_type=group_type,
                device=device,
                session=session,
                term=term,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    async def get(self, event_id: str) -> Event:
        """Returns the event with this id."""
        return await self._run(_events_get(event_id))


# Devices ------------------------------------------------------------------------------------


def _devices_list(
    *, identity: str | None, term: str | None, page_size: int | None, sort: str | None, order: str | None
) -> _ListCall[Device]:
    return _ListCall(
        "/devices", Device.from_api, {"identity": identity, "term": term}, page_size, sort, order
    )


def _device_path(fingerprint: str) -> str:
    return f"/devices/{_segment(fingerprint, 'A device fingerprint')}"


def _devices_get(fingerprint: str) -> _Call[Device]:
    return _Call("GET", _device_path(fingerprint), lambda p: Device.from_api(_as_mapping(p)))


def _devices_update(fingerprint: str, disregarded: bool) -> _Call[Device]:
    return _Call(
        "PATCH",
        _device_path(fingerprint),
        lambda p: Device.from_api(_as_mapping(p)),
        json={"disregarded": bool(disregarded)},
    )


class Devices(_Runner):
    """Read the devices Dregs has seen, and disregard them."""

    def list(
        self,
        *,
        identity: str | None = None,
        term: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Device]:
        """Returns one page of devices, most recently seen first.

        Args:
            identity: Only devices this identity was seen on.
            term: Free text matched against fingerprints, addresses, places, and user agents.
            page: The page to return, counting from 0.
            page_size: Items per page, at most 100.
            sort: The field to sort on, such as ``"lastSeenAt"`` or ``"country"``.
            order: ``"asc"`` or ``"desc"``.
        """
        call = _devices_list(identity=identity, term=term, page_size=page_size, sort=sort, order=order)

        return self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        identity: str | None = None,
        term: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Iterator[Device]:
        """Yields every device that matches, fetching pages as it goes. See :meth:`list`."""
        return self._walk(
            _devices_list(identity=identity, term=term, page_size=page_size, sort=sort, order=order)
        )

    def get(self, fingerprint: str) -> Device:
        """Returns the device with this fingerprint.

        Raises:
            NotFoundError: No device has this fingerprint.
        """
        return self._run(_devices_get(fingerprint))

    def update(self, fingerprint: str, *, disregarded: bool) -> Device:
        """Sets whether the device is disregarded, and returns it.

        A disregarded device, such as a shared office machine, no longer links the identities
        seen on it.

        Raises:
            NotFoundError: No device has this fingerprint.
        """
        return self._run(_devices_update(fingerprint, disregarded))


class AsyncDevices(_AsyncRunner):
    """The async twin of :class:`Devices`."""

    async def list(
        self,
        *,
        identity: str | None = None,
        term: str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Device]:
        """Returns one page of devices. See :meth:`Devices.list`."""
        call = _devices_list(identity=identity, term=term, page_size=page_size, sort=sort, order=order)

        return await self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        identity: str | None = None,
        term: str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> AsyncIterator[Device]:
        """Yields every device that matches. Use with ``async for``."""
        return self._walk(
            _devices_list(identity=identity, term=term, page_size=page_size, sort=sort, order=order)
        )

    async def get(self, fingerprint: str) -> Device:
        """Returns the device with this fingerprint."""
        return await self._run(_devices_get(fingerprint))

    async def update(self, fingerprint: str, *, disregarded: bool) -> Device:
        """Sets whether the device is disregarded, and returns it."""
        return await self._run(_devices_update(fingerprint, disregarded))


# Escalations --------------------------------------------------------------------------------

_ESCALATION_STATUSES = ("OPEN", "ACKNOWLEDGED", "CLOSED")


def _escalation_status(status: str) -> str:
    if not isinstance(status, str) or status.upper() not in _ESCALATION_STATUSES:
        raise ValueError("status is 'open', 'acknowledged', or 'closed'.")

    return status.upper()


def _escalations_list(
    *,
    status: str | None,
    severity: str | None,
    identity: str | None,
    rule: int | str | None,
    page_size: int | None,
    sort: str | None,
    order: str | None,
) -> _ListCall[Escalation]:
    filters = {
        "status": _escalation_status(status) if status is not None else None,
        "severity": severity.upper() if severity else None,
        "identity": identity,
        "rule": rule,
    }

    return _ListCall("/escalations", Escalation.from_api, filters, page_size, sort, order)


def _escalation_path(escalation_id: int | str) -> str:
    return f"/escalations/{_segment(str(escalation_id), 'An escalation id')}"


def _escalations_get(escalation_id: int | str) -> _Call[Escalation]:
    return _Call("GET", _escalation_path(escalation_id), lambda p: Escalation.from_api(_as_mapping(p)))


def _escalations_update(escalation_id: int | str, status: str) -> _Call[Escalation]:
    return _Call(
        "PATCH",
        _escalation_path(escalation_id),
        lambda p: Escalation.from_api(_as_mapping(p)),
        json={"status": _escalation_status(status)},
    )


def _escalations_summary() -> _Call[EscalationSummary]:
    return _Call("GET", "/escalations/summary", lambda p: EscalationSummary.from_api(_as_mapping(p)))


class Escalations(_Runner):
    """Read the escalations your escalation rules open, and move them along."""

    def list(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        identity: str | None = None,
        rule: int | str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Escalation]:
        """Returns one page of escalations, newest first.

        Args:
            status: Only escalations in this status: ``"open"``, ``"acknowledged"``, or
                ``"closed"``.
            severity: Only escalations of this severity: ``"info"``, ``"warning"``, or
                ``"critical"``.
            identity: Only escalations about this identity.
            rule: Only escalations opened by the escalation rule with this id.
            page: The page to return, counting from 0.
            page_size: Items per page, at most 100.
            sort: The field to sort on, such as ``"openedAt"`` or ``"severity"``.
            order: ``"asc"`` or ``"desc"``.
        """
        call = _escalations_list(
            status=status,
            severity=severity,
            identity=identity,
            rule=rule,
            page_size=page_size,
            sort=sort,
            order=order,
        )

        return self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        identity: str | None = None,
        rule: int | str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Iterator[Escalation]:
        """Yields every escalation that matches, fetching pages as it goes. See :meth:`list`."""
        return self._walk(
            _escalations_list(
                status=status,
                severity=severity,
                identity=identity,
                rule=rule,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    def get(self, escalation_id: int | str) -> Escalation:
        """Returns the escalation with this id.

        Raises:
            NotFoundError: No escalation has this id.
        """
        return self._run(_escalations_get(escalation_id))

    def update(self, escalation_id: int | str, *, status: str) -> Escalation:
        """Moves the escalation to ``status`` (``"open"``, ``"acknowledged"``, or ``"closed"``).

        Raises:
            NotFoundError: No escalation has this id.
        """
        return self._run(_escalations_update(escalation_id, status))

    def summary(self) -> EscalationSummary:
        """Returns how many escalations are open, acknowledged, and closed."""
        return self._run(_escalations_summary())


class AsyncEscalations(_AsyncRunner):
    """The async twin of :class:`Escalations`."""

    async def list(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        identity: str | None = None,
        rule: int | str | None = None,
        page: int = 0,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> Page[Escalation]:
        """Returns one page of escalations. See :meth:`Escalations.list`."""
        call = _escalations_list(
            status=status,
            severity=severity,
            identity=identity,
            rule=rule,
            page_size=page_size,
            sort=sort,
            order=order,
        )

        return await self._run(call.page(_page_number(page)))

    def list_all(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        identity: str | None = None,
        rule: int | str | None = None,
        page_size: int | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> AsyncIterator[Escalation]:
        """Yields every escalation that matches. Use with ``async for``."""
        return self._walk(
            _escalations_list(
                status=status,
                severity=severity,
                identity=identity,
                rule=rule,
                page_size=page_size,
                sort=sort,
                order=order,
            )
        )

    async def get(self, escalation_id: int | str) -> Escalation:
        """Returns the escalation with this id."""
        return await self._run(_escalations_get(escalation_id))

    async def update(self, escalation_id: int | str, *, status: str) -> Escalation:
        """Moves the escalation to ``status``."""
        return await self._run(_escalations_update(escalation_id, status))

    async def summary(self) -> EscalationSummary:
        """Returns how many escalations are open, acknowledged, and closed."""
        return await self._run(_escalations_summary())


def _as_mapping(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _as_sequence(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    return [item for item in payload if isinstance(item, dict)]
