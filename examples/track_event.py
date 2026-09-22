"""Send a backend event to Dregs.

Run it with your credential's secret key in the environment:

    DREGS_SECRET_KEY=sk_... uv run python examples/track_event.py
"""

from __future__ import annotations

from dregs import Dregs, DregsError, QuotaExceededError, RateLimitError


def main() -> None:
    with Dregs() as client:
        try:
            result = client.track(
                "user.signup",
                identity="user_12345",
                # Attributes of the event.
                data={"plan": "pro", "referrer": "partner-x"},
                # Attributes of the user. The analyzers lean on these, so send what you have.
                identity_data={
                    "email": "ada@example.com",
                    "name": "Ada Lovelace",
                    "username": "ada",
                },
                # Your own id for the event makes ingestion idempotent: resending this exact
                # call is a no-op rather than a second signup.
                event_id="signup-991",
            )
        except QuotaExceededError:
            print("Over the monthly event limit. The event was not recorded.")

            return
        except RateLimitError as exc:
            print(f"Rate limited. Retry after {exc.retry_after or 'a moment'}.")

            return
        except DregsError as exc:
            print(f"Could not reach Dregs: {exc}")

            return

        if result.accepted:
            print(f"Recorded event {result.id}.")
        else:
            # Uncommon, and worth a log line: accepted without an event being recorded.
            print(f"The event was not recorded (status {result.status}).")


if __name__ == "__main__":
    main()
