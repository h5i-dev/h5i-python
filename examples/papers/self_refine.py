"""Self-Refine: Iterative Refinement with Self-Feedback (Madaan et al. 2023,
arXiv:2303.17651) — the generate → FEEDBACK → REFINE loop.

One model plays two roles with two prompts: it generates a candidate,
critiques its own output, then refines against that critique — no external
signal, no training. That maps to a single seat: ``reflect`` is the FEEDBACK
step, a first-class self-feedback turn recorded as a reflection (never as a
peer review — reviews stay peer-to-peer in h5i), and ``revise`` is REFINE.
The loop stops when the agent's own critique approves (the ``APPROVE``
first-line convention) or the round budget runs out.

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

        # Generate: one independent attempt, then seal the round.
        artifact = await author.work(task, expect_independent=True)
        await c.freeze()

        # Feedback → refine, until the author's own critique approves or the
        # budget is spent. Reflections create no influence edge — the refined
        # candidate stays stamped independent.
        refinements = 0
        for _ in range(MAX_ROUNDS):
            feedback = await author.reflect(artifact)
            if feedback.approved:
                break
            refinements += 1
            artifact = await author.revise(artifact, feedback)

        print(f"refined {refinements} time(s); final candidate {artifact.id}")

        # Not part of Self-Refine — finalize the run so the journal ends with
        # neutral evidence and a recorded verdict.
        await c.verify(artifact, ["pytest", "-q"])
        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
