"""Judge panel: LLM judgment over *recorded evidence*, not vibes.

Workers attempt the task independently and a neutral verifier runs; then a
panel of judge agents scores every sealed candidate 0-10 against a rubric,
citing the artifact/verification ids they used. Hallucinated citations are
re-asked (bounded); the mean-score winner is recorded as an advisory verdict
(never auto-applicable — apply stays a human decision).

Judges are read-only seats that must be hired before the round seals —
alongside the workers, exactly like the roster note in patterns.py says.

    python examples/judge_panel_score.py
"""

import asyncio

from h5i.orchestra import Conductor, patterns

TASK = "reduce `h5i team status` latency without changing its output"
RUBRIC = (
    "prefer the smallest change that demonstrably keeps behavior identical; "
    "penalize speculative refactors and untested hot paths"
)


async def main() -> None:
    async with Conductor(".", "panel-demo", launcher="resident") as c:
        workers = await asyncio.gather(
            c.hire("claude", runtime="claude", model="claude-haiku-4-5"),
            c.hire("codex", runtime="codex", model="gpt-5.4-mini"),
        )
        judges = await asyncio.gather(
            c.hire("judge-a", runtime="claude", model="claude-haiku-4-5"),
            c.hire("judge-b", runtime="claude", model="claude-haiku-4-5"),
        )

        # Independent attempts → seal → neutral evidence for the panel.
        artifacts = await asyncio.gather(
            *(w.work(TASK, expect_independent=True) for w in workers)
        )
        await c.freeze()
        for artifact in artifacts:
            await c.verify(artifact, ["cargo", "test", "--quiet"])

        outcome = await patterns.judge_panel(c, RUBRIC, judges)

        for judge_id, ballots in outcome.ballots:
            for ballot in ballots:
                print(
                    f"{judge_id}: {ballot.artifact_id} = {ballot.score}/10 "
                    f"(cites {', '.join(ballot.cited_ids) or 'nothing'}) — "
                    f"{ballot.rationale}"
                )
        print("panel verdict:", outcome.verdict.selected_submission,
              "—", *outcome.verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main())
