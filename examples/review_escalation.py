"""Escalation ladder: a cheap agent tries first; a senior reviews; if two
revise cycles don't earn approval, the senior takes over with the junior's
artifact granted as material — nothing is thrown away.

This is `if`/`for` doing what a workflow language would need three node types
for. Both seats are hired up front (enrollment is open-round-only), so the
escalation path exists from the start whether or not it's taken.

    python examples/review_escalation.py "fix the flaky msg_integration test"
"""

import asyncio
import sys

from h5i.orchestra import Conductor

MAX_REVISE_CYCLES = 2


async def main(task: str) -> None:
    async with Conductor(".", "escalation-demo", launcher="resident") as c:
        junior = await c.hire("junior", runtime="claude", model="claude-haiku-4-5")
        senior = await c.hire(
            "senior", runtime="claude", model="claude-haiku-4-5"
        )

        artifact = await junior.work(task)
        await c.freeze()

        approved = False
        for cycle in range(MAX_REVISE_CYCLES):
            review = await senior.review(artifact)
            if review.approved:
                approved = True
                break
            print(f"cycle {cycle + 1}: senior rejected — {review.body[:100]}…")
            artifact = await junior.revise(artifact, review)

        if not approved:
            review = await senior.review(artifact)
            approved = review.approved

        if not approved:
            # Escalate: the senior builds on the junior's attempt rather than
            # from scratch — the material grant records the influence edge.
            await c.note(f"escalating to senior after {MAX_REVISE_CYCLES} cycles")
            artifact = await senior.work(
                f"{task}\n\nA junior attempt is granted as material. Salvage "
                "what is right, fix what its reviews flagged, and submit a "
                "candidate you would approve.",
                materials=[artifact],
            )

        verification = await c.verify(artifact, ["cargo", "test", "--quiet"])
        print(
            f"final candidate by {artifact.owner_agent}: "
            f"tests_passed={verification.tests_passed}"
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "demo task"))
