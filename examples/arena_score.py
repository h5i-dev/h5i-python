"""Arena: N independent attempts, ranked — when you want the best of several
tries, not a consensus.

Every agent gets the same task with no cross-influence (independence is
validated at submit time, not promised), the round seals, one neutral
verifier command runs against every candidate, and the built-in policy picks
the smallest green diff. The compare rows are the same arena view
`h5i team compare` renders.

    python examples/arena_score.py "make `h5i doctor` exit non-zero on repair failures"
"""

import asyncio
import sys

from h5i.orchestra import Conductor, patterns


async def main(task: str) -> None:
    async with Conductor(".", "arena-demo", launcher="resident") as c:
        agents = await asyncio.gather(
            c.hire("claude", runtime="claude"),
            c.hire("codex", runtime="codex"),
            c.hire("haiku", runtime="claude", model="claude-haiku-4-5"),
        )
        await c.preflight(live=agents, clean_worktree=True)

        outcome = await patterns.arena(
            c,
            task,
            agents,
            verify=["cargo", "test", "--quiet"],
            isolation="process",
        )

        for row in outcome.rows:
            print(
                f"{row.agent_id:>8}  submitted={row.submitted}  "
                f"+{row.insertions}/-{row.deletions} over {row.files_changed} files  "
                f"status={row.status}"
            )
        verdict = outcome.verdict
        assert verdict is not None
        print("verdict:", verdict.selected_submission, "—", *verdict.reasons)

        # Apply stays an explicit decision, behind a durable human gate.
        if verdict.selected_submission and (await c.gate("apply the winner?")).approved:
            winner = next(
                a for a in outcome.artifacts if a.id == verdict.selected_submission
            )
            print("applied:", (await c.apply(winner)).target_commit_oid)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "demo task"))
