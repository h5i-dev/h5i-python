"""Tree of Thoughts: Deliberate Problem Solving with Large Language Models
(Yao et al. 2023, arXiv:2305.10601) — breadth-first search over partial
plans, then build the best leaf.

A thought is one coherent planning step; a state is the plan so far. Each
level: a proposer expands every frontier state into k candidate thoughts,
an evaluator scores all new states in one vote turn, and the best b survive
(beam search — the paper's BFS variant). Search runs on cheap ``ask`` data
turns; only the winning plan pays for a real work turn. Backtracking falls
out of the beam: a state whose children all score poorly simply stops being
expanded.

    python examples/papers/tree_of_thoughts.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Conductor

DEMO_TASK = "implement quicksort with pytest"
K_THOUGHTS = 3  # thoughts proposed per state
BEAM = 2  # states kept per level
DEPTH = 2  # levels of the tree


def parse_thoughts(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("reply must be a non-empty JSON array of strings")
    return [str(t).strip() for t in value][:K_THOUGHTS]


def parse_scores(expected: int):
    def parse(value: Any) -> list[float]:
        scores = value.get("scores") if isinstance(value, dict) else value
        if not isinstance(scores, list) or len(scores) != expected:
            raise ValueError(f'reply must be {{"scores": [<{expected} numbers 0-10>]}}')
        return [max(0.0, min(10.0, float(s))) for s in scores]

    return parse


async def main(task: str) -> None:
    async with Conductor(".", "tot-demo", launcher="resident", isolation="supervised") as c:
        proposer = await c.hire("proposer", runtime="claude", model="claude-haiku-4-5")
        evaluator = await c.hire("evaluator", runtime="claude", model="claude-haiku-4-5")
        builder = await c.hire("builder", runtime="codex", model="gpt-5.4-mini", effort="medium")

        # BFS with a beam: expand every frontier state, score, keep the top b.
        frontier: list[str] = [""]
        for depth in range(1, DEPTH + 1):
            children: list[str] = []
            for state in frontier:  # one proposer seat → sequential expansion
                thoughts = await proposer.ask(
                    f"Task: {task}\n\nPlan so far:\n{state or '(empty)'}\n"
                    f"Propose {K_THOUGHTS} DISTINCT candidate next steps — "
                    "different strategies, not rephrasings. Reply as a JSON "
                    "array of strings.",
                    parse=parse_thoughts,
                )
                children.extend(f"{state}{depth}. {t}\n" for t in thoughts)

            numbered = "\n".join(
                f"--- candidate {i + 1} ---\n{s}" for i, s in enumerate(children)
            )
            scores = await evaluator.ask(
                f"Task: {task}\n\nCandidate partial plans:\n{numbered}\n"
                "Score how promising each plan is as a path to a correct, "
                "complete solution (0-10). Reply as JSON: "
                f'{{"scores": [<{len(children)} numbers>]}}',
                parse=parse_scores(len(children)),
            )
            ranked = sorted(zip(scores, children), key=lambda p: -p[0])
            frontier = [state for _, state in ranked[:BEAM]]
            print(f"depth {depth}: kept {len(frontier)}/{len(children)} states "
                  f"(best score {ranked[0][0]:.1f})")

        best = frontier[0]
        print(f"\nchosen plan:\n{best}")

        # Only the winning leaf pays for a real work turn.
        artifact = await builder.work(f"{task}\n\nFollow this plan:\n{best}")
        await c.freeze()
        await c.verify(artifact, ["pytest", "-q"])
        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
