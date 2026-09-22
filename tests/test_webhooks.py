"""Webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from dregs import WebhookVerificationError
from dregs.webhooks import compute_signature, verify, verify_signature

SECRET = "whsec_abc123"
SENT_AT = datetime(2026, 9, 21, 14, 22, 9, tzinfo=timezone.utc)


def _payload(**overrides: object) -> bytes:
    body: dict[str, object] = {
        "event": "ESCALATION_CREATED",
        "timestamp": SENT_AT.isoformat().replace("+00:00", "Z"),
        "identityId": "user_12345",
    }

    body.update(overrides)

    return json.dumps(body).encode("utf-8")


def _sign(payload: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class TestComputeSignature:
    def test_matches_a_hand_rolled_hmac(self) -> None:
        payload = _payload()

        assert compute_signature(payload, SECRET) == _sign(payload)

    def test_accepts_a_string_body(self) -> None:
        payload = _payload()

        assert compute_signature(payload.decode(), SECRET) == compute_signature(payload, SECRET)


class TestVerifySignature:
    def test_a_good_signature_verifies(self) -> None:
        payload = _payload()

        assert verify_signature(payload, _sign(payload), SECRET) is True

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        payload = _payload()

        assert verify_signature(payload, f"  {_sign(payload)}\n", SECRET) is True

    def test_a_tampered_body_fails(self) -> None:
        signature = _sign(_payload())

        assert verify_signature(_payload(identityId="someone_else"), signature, SECRET) is False

    def test_the_wrong_secret_fails(self) -> None:
        payload = _payload()

        assert verify_signature(payload, _sign(payload, "whsec_other"), SECRET) is False

    def test_an_empty_signature_fails(self) -> None:
        assert verify_signature(_payload(), "", SECRET) is False

    def test_an_empty_secret_fails(self) -> None:
        payload = _payload()

        assert verify_signature(payload, _sign(payload), "") is False


class TestVerify:
    def test_returns_the_parsed_event(self) -> None:
        payload = _payload()

        event = verify(payload, _sign(payload), SECRET, now=SENT_AT)

        assert event["event"] == "ESCALATION_CREATED"
        assert event["identityId"] == "user_12345"

    def test_a_bad_signature_raises(self) -> None:
        with pytest.raises(WebhookVerificationError, match="signature"):
            verify(_payload(), "deadbeef", SECRET, now=SENT_AT)

    def test_a_body_that_is_not_json_raises(self) -> None:
        payload = b"not json at all"

        with pytest.raises(WebhookVerificationError, match="JSON"):
            verify(payload, _sign(payload), SECRET)

    def test_a_json_array_body_raises(self) -> None:
        payload = b"[1, 2, 3]"

        with pytest.raises(WebhookVerificationError, match="JSON object"):
            verify(payload, _sign(payload), SECRET)

    def test_a_stale_payload_is_refused_as_a_replay(self) -> None:
        payload = _payload()

        with pytest.raises(WebhookVerificationError, match="replay"):
            verify(payload, _sign(payload), SECRET, now=SENT_AT + timedelta(hours=1))

    def test_a_payload_inside_the_tolerance_is_accepted(self) -> None:
        payload = _payload()

        event = verify(payload, _sign(payload), SECRET, now=SENT_AT + timedelta(seconds=120))

        assert event["event"] == "ESCALATION_CREATED"

    def test_the_freshness_check_can_be_waived(self) -> None:
        payload = _payload()

        event = verify(payload, _sign(payload), SECRET, tolerance=None, now=SENT_AT + timedelta(days=30))

        assert event["event"] == "ESCALATION_CREATED"

    def test_a_missing_timestamp_raises_unless_the_check_is_waived(self) -> None:
        payload = json.dumps({"event": "ESCALATION_CREATED"}).encode()

        with pytest.raises(WebhookVerificationError, match="no timestamp"):
            verify(payload, _sign(payload), SECRET)

        assert verify(payload, _sign(payload), SECRET, tolerance=None)["event"] == "ESCALATION_CREATED"

    def test_an_unreadable_timestamp_raises(self) -> None:
        payload = _payload(timestamp="the day before yesterday")

        with pytest.raises(WebhookVerificationError, match="unreadable"):
            verify(payload, _sign(payload), SECRET)

    def test_a_naive_reference_time_is_read_as_utc(self) -> None:
        payload = _payload()

        event = verify(payload, _sign(payload), SECRET, now=SENT_AT.replace(tzinfo=None))

        assert event["event"] == "ESCALATION_CREATED"
