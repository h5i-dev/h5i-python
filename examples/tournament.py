"""Tournament bracket: semifinals → final, each match its own arena *run*.

A team run seals once, so a bracket doesn't fit inside one run — and it
doesn't need to: a Conductor is just an object, so multi-run orchestration is
a Python function calling another. Each match journals independently, which
means a killed bracket resumes mid-tournament — finished matches replay their
recorded verdicts instantly.

    python examples/tournament.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, patterns

DEMO_TASK = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]

#: (name, runtime, model) seeds, bracket order.
SEEDS = [
    ("claude", "claude", "claude-haiku-4-5"),
    ("codex", "codex", "gpt-5.4-mini"),
    ("haiku", "claude", "claude-haiku-4-5"),
    ("haiku-2", "claude", "claude-haiku-4-5"),
]


async def match(
    run_id: str, task: str, contenders: list[tuple[str, str, str | None]]
) -> tuple[str, str, str | None]:
    """One arena run; returns the winning seed."""
    async with Conductor(".", run_id, launcher="resident", isolation="supervised") as c:
        agents = {
            name: await c.hire(name, runtime=runtime, model=model)
            for name, runtime, model in contenders
        }
        outcome = await patterns.arena(c, task, list(agents.values()), verify=VERIFY)
        verdict = outcome.verdict
        assert verdict is not None
        winner_artifact = next(
            (a for a in outcome.artifacts if a.id == verdict.selected_submission), None
        )
        if winner_artifact is None:
            raise RuntimeError(f"{run_id}: no candidate survived verification")
        winner = next(s for s in contenders if s[0] == winner_artifact.owner_agent)
        print(f"{run_id}: {winner[0]} wins — {'; '.join(verdict.reasons)}")
        return winner


async def main(task: str) -> None:
    # Semifinals run concurrently — separate runs, separate envs, no shared
    # journal labels to collide.
    finalist_a, finalist_b = await asyncio.gather(
        match("bracket-semi-1", task, [SEEDS[0], SEEDS[3]]),
        match("bracket-semi-2", task, [SEEDS[1], SEEDS[2]]),
    )
    champion = await match("bracket-final", task, [finalist_a, finalist_b])
    print("champion:", champion[0])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
