"""Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et
al. 2023, arXiv:2303.11366) — actor / evaluator / self-reflection.

The actor attempts the task; an evaluator returns a sparse pass/fail; on
failure the actor verbalizes *why* it failed, and that reflection lands in
an episodic memory that rides along with every later trial. No weights move
— the "reinforcement" is text. The h5i mapping: the evaluator is
``conductor.verify`` (a real command in a fresh worktree, not an LLM
opinion), the reflection is an ``ask`` data turn, and the episodic memory is
delivered as a constructed ``Review`` the actor revises against — so every
trial, reflection, and retry is journaled and resumable.

    python examples/papers/reflexion.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, Review, Verification

DEMO_TASK = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]
MAX_TRIALS = 3


def describe(v: Verification) -> str:
    line = (
        f"`{' '.join(v.command)}`: "
        + ("applied cleanly" if v.applies_cleanly else "failed to apply")
        + ", "
        + ("tests passed" if v.tests_passed else "tests failed")
    )
    if v.failure:
        line += f"\nfailure: {v.failure}"
    return line


async def main(task: str) -> None:
    async with Conductor(".", "reflexion-demo", launcher="resident", isolation="supervised") as c:
        actor = await c.hire("actor", runtime="claude", model="claude-haiku-4-5")

        artifact = await actor.work(task, expect_independent=True)
        await c.freeze()

        memory: list[str] = []  # the episodic reflection buffer
        for trial in range(1, MAX_TRIALS + 1):
            verification = await c.verify(artifact, VERIFY)
            if verification.applies_cleanly and verification.tests_passed:
                print(f"trial {trial}: evaluator is green")
                break
            evidence = describe(verification)
            print(f"trial {trial}: evaluator rejected ({evidence.splitlines()[0]})")
            if trial == MAX_TRIALS:
                break

            # Self-reflection: turn the sparse fail signal into a verbal lesson.
            reflection = await actor.ask(
                "Your submission failed neutral verification.\n"
                f"{evidence}\n\n"
                "Reflect: in 2-3 sentences, state what likely went wrong and "
                "what you will do differently next trial. Reply as a single "
                "JSON string.",
                parse=lambda v: v if isinstance(v, str) else str(v),
            )
            memory.append(reflection)

            # Next trial: the whole episodic memory rides in as the review.
            lessons = "\n".join(f"- {r}" for r in memory)
            artifact = await actor.revise(
                artifact,
                Review(
                    reviewer="reflexion-memory",
                    target=actor.id,
                    round=artifact.round,
                    body=(
                        "Verdict: REVISE\n\nYour reflections from earlier "
                        f"trials:\n{lessons}\n\nApply these lessons and fix "
                        f"the failure:\n{evidence}"
                    ),
                    referenced_artifacts=(artifact.id,),
                ),
            )

        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
