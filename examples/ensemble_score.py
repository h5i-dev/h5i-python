"""A complete score: two agents attempt a task, cross-review, get neutrally
verified, and a policy picks a winner behind a durable human gate.

Run it, kill it at any point, run it again — journaled steps replay and the
run continues where it stopped. Resident agent sessions are expected to be
attached (bring them up with `launcher="resident"` to let the score spawn
tmux sessions itself).

    python examples/ensemble_score.py "implement `h5i pull` mirroring `h5i push`"
"""

import asyncio
import sys

from h5i.orchestra import Conductor


async def main(task: str) -> None:
    async with Conductor(".", "ensemble-demo", launcher="resident") as c:
        claude = await c.hire("claude", runtime="claude")
        codex = await c.hire("codex", runtime="codex")

        # Fail the predictable ways now, not at minute 30.
        # LaunchResident starts each session on its first turn, so there is no
        # live session to check yet.  Still fail fast on repository hygiene.
        await c.preflight(clean_worktree=True)

        # Independent attempts, in parallel — then seal the round.
        a, b = await asyncio.gather(
            claude.work(task, expect_independent=True),
            codex.work(task, expect_independent=True),
        )
        await c.freeze()

        # Cross-review; revise only what a reviewer rejected.
        review_of_a, review_of_b = await asyncio.gather(
            codex.review(a), claude.review(b)
        )
        if not review_of_a.approved:
            a = await claude.revise(a, review_of_a)
        if not review_of_b.approved:
            b = await codex.revise(b, review_of_b)

        # Neutral verification in fresh sandboxed worktrees (never the
        # author's box), then the built-in verdict rule.
        await c.verify(a, ["cargo", "test", "--quiet"])
        await c.verify(b, ["cargo", "test", "--quiet"])
        verdict = await c.judge()

        print(await c.trace())
        if verdict.selected_submission is None:
            print("no candidate survived verification")
            return

        # A durable human gate: if nobody answers, exit and re-run later —
        # the question is not re-asked, the wait resumes.
        winner = a if verdict.selected_submission == a.id else b
        answer = await c.gate(
            f"apply {winner.id} by {winner.owner_agent}? ({verdict.reasons})"
        )
        if answer.approved:
            result = await c.apply(winner)
            print("applied:", result.target_commit_oid)
        else:
            print("declined:", answer.body)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "demo task"))
