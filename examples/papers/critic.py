"""CRITIC: Large Language Models Can Self-Correct with Tool-Interactive
Critiquing (Gou et al. 2024, arXiv:2305.11738) — verify → critique → correct.

A model's unaided opinion of its own output is unreliable, so CRITIC grounds
every critique in *external tools*. Each cycle: run the toolbox against the
candidate (``conductor.verify``, one neutral command per tool, each in a
fresh sandboxed worktree), have the same model read the raw tool evidence
and turn it into a concrete critique (an ``ask`` data turn), then correct
against that critique (``revise``). All tools green ends the loop. Extend
``TOOLS`` with linters or scanners to widen the toolbox.

    python examples/papers/critic.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, Review, Verification

DEMO_TASK = "implement quicksort with pytest"
TOOLS: tuple[list[str], ...] = (
    ["python", "-m", "compileall", "-q", "."],
    ["pytest", "-q"],
)
MAX_CYCLES = 3


def describe(v: Verification) -> str:
    line = (
        f"`{' '.join(v.command)}`: "
        + ("applied cleanly" if v.applies_cleanly else "failed to apply")
        + ", "
        + ("passed" if v.tests_passed else "FAILED")
    )
    if v.failure:
        line += f" — {v.failure}"
    return line


async def main(task: str) -> None:
    async with Conductor(".", "critic-demo", launcher="resident", isolation="supervised") as c:
        solver = await c.hire("solver", runtime="claude", model="claude-haiku-4-5")

        artifact = await solver.work(task, expect_independent=True)
        await c.freeze()

        for cycle in range(1, MAX_CYCLES + 1):
            # Interact with the tools: neutral evidence, not self-opinion.
            runs = [await c.verify(artifact, tool) for tool in TOOLS]
            evidence = "\n".join(describe(v) for v in runs)
            if all(v.applies_cleanly and v.tests_passed for v in runs):
                print(f"cycle {cycle}: all {len(TOOLS)} tools green")
                break
            print(f"cycle {cycle}: tools rejected the candidate")
            if cycle == MAX_CYCLES:
                break

            # Critique conditioned on the tool outputs.
            critique = await solver.ask(
                "External tools ran against your submission:\n"
                f"{evidence}\n\n"
                "Write a tool-grounded critique: list each concrete problem "
                "the evidence shows and the fix you will make. Reply as a "
                "single JSON string.",
                parse=lambda v: v if isinstance(v, str) else str(v),
            )

            # Correct against the critique.
            artifact = await solver.revise(
                artifact,
                Review(
                    reviewer="tool-critic",
                    target=solver.id,
                    round=artifact.round,
                    body=f"Verdict: REVISE\n\n{critique}\n\nTool evidence:\n{evidence}",
                    referenced_artifacts=(artifact.id,),
                ),
            )

        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
