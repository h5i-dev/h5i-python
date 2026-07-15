"""Teaching Large Language Models to Self-Debug (Chen et al. 2023,
arXiv:2304.05128) — rubber-duck debugging: explain your own code before
fixing it.

Self-Debug's key finding: even without any error message, making the model
*explain its code line by line* surfaces the bug — and with real execution
feedback it works better still. Each cycle here: neutral execution
(``conductor.verify``), then an explanation ``ask`` (the rubber-duck step
— what does each part actually do, where could the observed failure come
from?), then a revise turn against the explanation + evidence. Compare
``reflexion.py`` (lessons about the *approach*) and ``critic.py`` (tool
outputs alone): here the feedback is the model's own code walkthrough.

    python examples/papers/self_debugging.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, Review, Verification

DEMO_TASK = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]
MAX_CYCLES = 3


def describe(v: Verification) -> str:
    line = (
        f"`{' '.join(v.command)}`: "
        + ("applied cleanly" if v.applies_cleanly else "failed to apply")
        + ", "
        + ("tests passed" if v.tests_passed else "tests FAILED")
    )
    if v.failure:
        line += f"\nfailure: {v.failure}"
    return line


async def main(task: str) -> None:
    async with Conductor(".", "selfdebug-demo", launcher="resident", isolation="supervised") as c:
        coder = await c.hire("coder", runtime="claude", model="claude-haiku-4-5")

        artifact = await coder.work(task, expect_independent=True)
        await c.freeze()

        for cycle in range(1, MAX_CYCLES + 1):
            verification = await c.verify(artifact, VERIFY)
            if verification.applies_cleanly and verification.tests_passed:
                print(f"cycle {cycle}: green")
                break
            evidence = describe(verification)
            print(f"cycle {cycle}: failed — rubber-duck round")
            if cycle == MAX_CYCLES:
                break

            # The rubber-duck step: explain the code, then locate the bug.
            explanation = await coder.ask(
                "Your submission failed:\n"
                f"{evidence}\n\n"
                "Rubber-duck it: walk through YOUR OWN code section by "
                "section — what each part actually does (not what it is "
                "meant to do) — then state where the observed failure most "
                "likely comes from. Reply as a single JSON string.",
                parse=lambda v: v if isinstance(v, str) else str(v),
            )

            artifact = await coder.revise(
                artifact,
                Review(
                    reviewer="rubber-duck",
                    target=coder.id,
                    round=artifact.round,
                    body=(
                        "Verdict: REVISE\n\nYour own walkthrough of the "
                        f"code:\n{explanation}\n\nExecution evidence:\n"
                        f"{evidence}\n\nFix the located bug."
                    ),
                    referenced_artifacts=(artifact.id,),
                ),
            )

        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
