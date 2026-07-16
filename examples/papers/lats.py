"""Language Agent Tree Search Unifies Reasoning, Acting, and Planning in
Language Models (Zhou et al. 2024, arXiv:2310.04406) — MCTS over real
attempts, with environment reward and reflections.

LATS runs Monte Carlo tree search where a node is an actual attempt, not a
hypothetical thought: expansion is a revise turn, the reward blends real
environment feedback (here ``conductor.verify``) with an LLM value
estimate, values back-propagate to the root, and failed nodes leave
Reflexion-style reflections that steer later expansions. UCT selection,
expansion, evaluation, and backprop are ~30 lines of plain Python; every
turn in the tree is journaled, so an interrupted search resumes mid-tree.

    python examples/papers/lats.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import math
import sys
from dataclasses import dataclass, field
from typing import Any

from h5i.orchestra import Artifact, Conductor, Review, Verification

DEMO_TASK = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]
MAX_EXPANSIONS = 3
EXPLORATION = 1.0  # UCT exploration constant


@dataclass
class Node:
    artifact: Artifact
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    visits: int = 0
    total_value: float = 0.0
    reflection: str = ""
    green: bool = False


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


def parse_value(value: Any) -> float:
    score = value.get("score") if isinstance(value, dict) else value
    return max(0.0, min(10.0, float(score)))


def uct(node: Node, parent_visits: int) -> float:
    if node.visits == 0:
        return float("inf")
    exploit = node.total_value / node.visits
    return exploit + EXPLORATION * math.sqrt(math.log(parent_visits) / node.visits)


def select(root: Node) -> Node:
    node = root
    while node.children:
        node = max(node.children, key=lambda ch: uct(ch, max(1, node.visits)))
    return node


def backpropagate(node: Node, value: float) -> None:
    cursor: Node | None = node
    while cursor is not None:
        cursor.visits += 1
        cursor.total_value += value
        cursor = cursor.parent


def lineage_reflections(node: Node) -> list[str]:
    out: list[str] = []
    cursor: Node | None = node
    while cursor is not None:
        if cursor.reflection:
            out.append(cursor.reflection)
        cursor = cursor.parent
    return list(reversed(out))


async def main(task: str) -> None:
    async with Conductor(".", "lats-demo", launcher="resident", isolation="supervised") as c:
        solver = await c.hire("solver", runtime="claude", model="claude-haiku-4-5")
        valuer = await c.hire("valuer", runtime="claude", model="claude-haiku-4-5")

        async def evaluate(node: Node) -> float:
            """Reward = real environment feedback + an LLM value estimate."""
            verification = await c.verify(node.artifact, VERIFY)
            if verification.applies_cleanly and verification.tests_passed:
                node.green = True
                return 10.0
            node.reflection = await solver.ask(
                "Your attempt failed neutral verification.\n"
                f"{describe(verification)}\n\nIn 1-2 sentences: what went "
                "wrong, and what should the NEXT attempt do differently? "
                "Reply as a single JSON string.",
                parse=lambda v: v if isinstance(v, str) else str(v),
            )
            estimate = await valuer.ask(
                f"Task: {task}\nAn attempt failed verification with:\n"
                f"{describe(verification)}\nIts author reflected: "
                f"{node.reflection}\nHow close is this attempt to a working "
                'solution? Reply as JSON: {"score": <0-10>}',
                parse=parse_value,
            )
            return estimate

        # Root: one real attempt, then seal the round.
        root = Node(await solver.work(task, expect_independent=True))
        await c.freeze()
        backpropagate(root, await evaluate(root))

        expansions = 0
        best = root
        while not best.green and expansions < MAX_EXPANSIONS:
            leaf = select(root)
            lessons = lineage_reflections(leaf)
            child = Node(
                await solver.revise(
                    leaf.artifact,
                    Review(
                        reviewer="lats-search",
                        target=solver.id,
                        round=leaf.artifact.round,
                        body=(
                            "Verdict: REVISE\n\nReflections along this "
                            "branch of the search tree:\n"
                            + "\n".join(f"- {r}" for r in lessons)
                            + "\n\nProduce an improved attempt."
                        ),
                        referenced_artifacts=(leaf.artifact.id,),
                    ),
                ),
                parent=leaf,
            )
            leaf.children.append(child)
            expansions += 1
            value = await evaluate(child)
            backpropagate(child, value)
            print(f"expansion {expansions}: value {value:.1f}"
                  + (" (green)" if child.green else ""))
            if child.green or value > best.total_value / max(1, best.visits):
                best = child

        verdict = await c.judge()
        print(f"\nexplored {expansions} expansion(s); best node green={best.green}")
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
