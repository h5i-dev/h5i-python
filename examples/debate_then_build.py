"""Debate → build: settle a design question with argument before spending
implementation turns on it. Composition a manifest can't express — the
debate's conclusion *is* Python data, so it steers ordinary control flow.

Debate is pure `ask` (no artifacts, no freeze), so the winning side can go
straight into a work turn afterwards, in the same run and journal.

    python examples/debate_then_build.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, patterns

DEMO_TASK = "implement quicksort with pytest"


def question_for(task: str) -> str:
    return (
        f"What is the right way to '{task}'? pro argues for the simplest "
        "implementation that could work; con argues for the most robust, "
        "test-heavy one."
    )


async def main(task: str) -> None:
    question = question_for(task)
    async with Conductor(".", "debate-demo", launcher="resident", isolation="supervised") as c:
        pro = await c.hire("pro", runtime="claude", model="claude-haiku-4-5")
        con = await c.hire("con", runtime="codex", model="gpt-5.4-mini", effort="medium")
        moderator = await c.hire(
            "moderator", runtime="claude", model="claude-haiku-4-5"
        )

        outcome = await patterns.debate(
            c, question, [pro, con], moderator=moderator, rounds=2
        )
        for who, argument in outcome.transcript:
            print(f"[{who}] {argument[:120]}…")
        conclusion = outcome.conclusion
        assert conclusion is not None
        print(f"\nwinner: {conclusion.winner} — {conclusion.rationale}")

        # The verdict steers plain Python: the prevailing side implements its
        # own position; the loser writes the risk notes.
        winner = pro if conclusion.winner == pro.id else con
        loser = con if winner is pro else pro

        artifact, risks = await asyncio.gather(
            winner.work(
                f"You won this debate: {question}\nYour side prevailed with: "
                f"{conclusion.rationale}\nNow do the task your way: {task}"
            ),
            loser.ask(
                "You lost the debate. List the 3 biggest risks of the winning "
                'approach as a JSON array of strings, most severe first.',
                parse=lambda v: [str(x) for x in v],
            ),
        )
        await c.freeze()
        await c.note("debate risks: " + "; ".join(risks))
        print("built:", artifact.id, "| risks recorded to the event log")

        # Verify + judge so the run ends finalized: the sole submission gets
        # neutral verifier evidence and the built-in rule records a verdict,
        # leaving `h5i team apply` a one-liner for the human.
        await c.verify(artifact, ["pytest", "-q"])
        verdict = await c.judge()
        if verdict.selected_submission:
            print("verdict:", verdict.selected_submission, "—", *verdict.reasons)
            print("apply it with: h5i team apply debate-demo")
        else:
            print("no verdict:", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
