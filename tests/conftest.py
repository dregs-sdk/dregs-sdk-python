from __future__ import annotations

from collections.abc import Iterator

import pytest

from dregs import AsyncDregs, Dregs

BASE_URL = "https://api.test.invalid/api"
SECRET_KEY = "sk_abcdefghQijklmQabcdefghijklmn"


@pytest.fixture(autouse=True)
def _no_ambient_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps a developer's own DREGS_* variables out of the tests."""
    monkeypatch.delenv("DREGS_SECRET_KEY", raising=False)
    monkeypatch.delenv("DREGS_BASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapses retry backoff so the retry tests do not actually wait."""
    monkeypatch.setattr("dregs._base.BaseClient._backoff", lambda self, attempt, retry_after: 0.0)


@pytest.fixture
def client() -> Iterator[Dregs]:
    with Dregs(SECRET_KEY, base_url=BASE_URL, max_retries=0) as dregs:
        yield dregs


@pytest.fixture
def retrying_client() -> Iterator[Dregs]:
    with Dregs(SECRET_KEY, base_url=BASE_URL, max_retries=2) as dregs:
        yield dregs


@pytest.fixture
async def async_client() -> AsyncDregs:
    return AsyncDregs(SECRET_KEY, base_url=BASE_URL, max_retries=0)
