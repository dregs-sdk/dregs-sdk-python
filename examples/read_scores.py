"""Read an identity's scores, and the observations behind them.

DREGS_SECRET_KEY=sk_... uv run python examples/read_scores.py user_12345
"""

from __future__ import annotations

import sys

from dregs import Dregs, NotFoundError


def main() -> None:
    identity_id = sys.argv[1] if len(sys.argv) > 1 else "user_12345"

    with Dregs() as client:
        try:
            scores = client.identities.scores(identity_id)
        except NotFoundError:
            print(f"Dregs has never seen {identity_id}.")

            return

        if not scores:
            print(f"{identity_id} has not been scored yet. Scoring runs shortly after new activity.")

            return

        print(f"Scores for {identity_id}")
        print(f"  Humanity:     {_format(scores.humanity)}")
        print(f"  Authenticity: {_format(scores.authenticity)}")
        print(f"  Uniqueness:   {_format(scores.uniqueness)}")
        print(f"  Behavior:     {_format(scores.behavior)}")

        # The scores are the summary. The observations are the evidence, and they come from
        # the analysis cycle rather than from the scores endpoint.
        try:
            analysis = client.identities.analysis(identity_id)
        except NotFoundError:
            print("\nNo analysis cycle has finished for this identity yet.")

            return

        print(f"\nWhy, from the cycle of {analysis.finished_at:%Y-%m-%d %H:%M} UTC:")

        for observation in sorted(analysis.observations, key=lambda o: o.value or 1.0):
            print(f"  [{observation.category and observation.category.value}] {observation.label}")
            print(f"      {observation.explanation}")
            print(f"      value {observation.value}, confidence {observation.confidence}")


def _format(score: int | None) -> str:
    return "not scored" if score is None else str(score)


if __name__ == "__main__":
    main()
