"""CodeT: Code Generation with Generated Tests (Chen et al. 2022,
arXiv:2207.10397) — dual execution agreement: rank candidates by consensus
with an independent test suite.

Sample many solutions AND generate tests independently, then trust the
candidates the tests agree on: a solution's score is how well it passes
tests it never saw. Here n solution seats attempt the task in parallel
while a test designer writes the suite blind; after the freeze every
solution seat applies the granted suite as materials, each combined
candidate is neutrally executed, and a verdict policy ranks by agreement
(suite passed, then smaller diff). The consensus signal is per-suite; for
per-test granularity, parse the verifier's capture output.

    python examples/papers/codet.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, Verdict

DEMO_TASK = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]


async def main(task: str) -> None:
    async with Conductor(".", "codet-demo", launcher="resident", isolation="supervised") as c:
        solvers = [
            await c.hire("sol0", runtime="claude", model="claude-haiku-4-5"),
            await c.hire("sol1", runtime="claude", model="claude-haiku-4-5"),
            await c.hire("sol2", runtime="codex", model="gpt-5.4-mini", effort="medium"),
        ]
        test_designer = await c.hire(
            "test-designer", runtime="claude", model="claude-haiku-4-5"
        )

        # Solutions and tests sampled independently — neither sees the other.
        results = await asyncio.gather(
            *(s.work(task, expect_independent=True) for s in solvers),
            test_designer.work(
                f"Write ONLY a thorough test suite for: {task}\nCover basic, "
                "edge, and adversarial cases. Do NOT write the implementation.",
                expect_independent=True,
            ),
        )
        suite = results[-1]
        await c.freeze()

        # Dual execution: every solution takes on the same blind suite and
        # is neutrally executed against it.
        agreements: dict[str, bool] = {}
        for solver in solvers:
            candidate = await solver.work(
                "Apply the granted teammate artifact — an independently "
                "written test suite for your task — into your worktree "
                "alongside your implementation, WITHOUT changing either "
                "the tests or your implementation logic.",
                materials=[suite],
            )
            verification = await c.verify(candidate, VERIFY)
            agreements[candidate.id] = (
                verification.applies_cleanly and verification.tests_passed
            )
            print(
                f"{solver.id}: {'agrees with' if agreements[candidate.id] else 'rejected by'} "
                "the blind suite"
            )

        # Rank by dual execution agreement; ties go to the smaller diff.
        def dual_agreement(run) -> Verdict:
            candidates = [s for s in run.submissions if s.id in agreements]
            ranked = sorted(
                candidates,
                key=lambda s: (not agreements[s.id], s.files_changed, s.insertions, s.id),
            )
            winner = ranked[0]
            passing = sum(agreements.values())
            return Verdict(
                method=f"codet:dual-execution({passing}/{len(candidates)} agree)",
                decided_by="codet-demo score",
                selected_submission=winner.id if agreements[winner.id] else None,
                can_auto_apply=False,
                reasons=(
                    f"{winner.id} passed the independently generated suite"
                    if agreements[winner.id]
                    else "no candidate agreed with the blind test suite",
                ),
            )

        verdict = await c.judge(dual_agreement)
        print("\nverdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
