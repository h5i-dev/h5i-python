"""Debate → build: settle a design question with argument before spending
implementation turns on it. Composition a manifest can't express — the
debate's conclusion *is* Python data, so it steers ordinary control flow.

Debate is pure `ask` (no artifacts, no freeze), so the winning side can go
straight into a work turn afterwards, in the same run and journal.

    python examples/debate_then_build.py
"""

import asyncio

from h5i.orchestra import Conductor, patterns

QUESTION = (
    "Should `h5i msg wait` grow a --push webhook mode, or stay poll-only? "
    "pro argues for the webhook; con argues for polling."
)


async def main() -> None:
    async with Conductor(".", "debate-demo", launcher="resident") as c:
        pro = await c.hire("pro", runtime="claude", model="claude-haiku-4-5")
        con = await c.hire("con", runtime="codex", model="gpt-5.4-mini")
        moderator = await c.hire(
            "moderator", runtime="claude", model="claude-haiku-4-5"
        )

        outcome = await patterns.debate(
            c, QUESTION, [pro, con], moderator=moderator, rounds=2
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
                f"You won this debate: {QUESTION}\nYour side prevailed with: "
                f"{conclusion.rationale}\nImplement your position."
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


if __name__ == "__main__":
    asyncio.run(main())
