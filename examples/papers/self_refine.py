"""Self-Refine: Iterative Refinement with Self-Feedback (Madaan et al. 2023,
arXiv:2303.17651) — the generate → FEEDBACK → REFINE loop.

One model plays two roles with two prompts: it generates a candidate,
critiques its own output, then refines against that critique — no external
signal, no training. h5i forbids a seat from reviewing its own artifact
(reviews are provenance-tracked turns), so the critic role is a second seat
pinned to the *same* model: the paper's "self" is the model, not the
session. The loop stops when the critic approves (the ``APPROVE`` first-line
convention) or the round budget runs out.

    python examples/papers/self_refine.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor

DEMO_TASK = "implement quicksort with pytest"
MAX_ROUNDS = 3


async def main(task: str) -> None:
    async with Conductor(".", "self-refine-demo", launcher="resident", isolation="supervised") as c:
        author = await c.hire("author", runtime="claude", model="claude-haiku-4-5")
        critic = await c.hire("critic", runtime="claude", model="claude-haiku-4-5")

        # Generate: one independent attempt, then seal the round (review is
        # a sealed-phase turn).
        artifact = await author.work(task, expect_independent=True)
        await c.freeze()

        # Feedback → refine, until the critic approves or the budget is spent.
        refinements = 0
        for _ in range(MAX_ROUNDS):
            review = await critic.review(artifact)
            if review.approved:
                break
            refinements += 1
            artifact = await author.revise(artifact, review)

        print(f"refined {refinements} time(s); final candidate {artifact.id}")

        # Not part of Self-Refine — finalize the run so the journal ends with
        # neutral evidence and a recorded verdict.
        await c.verify(artifact, ["pytest", "-q"])
        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
