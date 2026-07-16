"""Graph of Thoughts: Solving Elaborate Problems with Large Language Models
(Besta et al. 2024, arXiv:2308.09687) — thought transformations on an
arbitrary DAG.

GoT generalizes chains and trees: a thought is a vertex, and the operations
are *generate* (branch k children), *score*, *keep-best*, *aggregate*
(merge several thoughts into a new one — the transformation trees cannot
express), and *refine* (a self-loop). Here each operation is one ``ask``
data turn and the graph is a plain Python dict of vertices and edges, so
the score prints the actual DAG it executed — the define-by-run journal is
the graph.

    python examples/papers/graph_of_thoughts.py ["<task>"]
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Conductor

DEMO_TASK = (
    "Design a step-by-step plan to migrate a small team's monolith web app "
    "to two or three services without a big-bang rewrite."
)
K_GENERATE = 3  # children of the root
KEEP_BEST = 2  # thoughts that survive scoring into the aggregate


def parse_thoughts(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("reply must be a non-empty JSON array of strings")
    return [str(t).strip() for t in value][:K_GENERATE]


def parse_scores(expected: int):
    def parse(value: Any) -> list[float]:
        scores = value.get("scores") if isinstance(value, dict) else value
        if not isinstance(scores, list) or len(scores) != expected:
            raise ValueError(f'reply must be {{"scores": [<{expected} numbers 0-10>]}}')
        return [max(0.0, min(10.0, float(s))) for s in scores]

    return parse


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


async def main(task: str) -> None:
    async with Conductor(".", "got-demo", launcher="resident", isolation="supervised") as c:
        generator = await c.hire("generator", runtime="claude", model="claude-haiku-4-5")
        scorer = await c.hire("scorer", runtime="claude", model="claude-haiku-4-5")
        merger = await c.hire("merger", runtime="claude", model="claude-haiku-4-5")

        # The graph: vertices are thoughts, edges record which operation
        # produced what from what.
        vertices: dict[str, str] = {"root": task}
        edges: list[tuple[str, str, str]] = []  # (from, op, to)

        # generate(k): branch the root into k independent approaches.
        approaches = await generator.ask(
            f"Task: {task}\n\nPropose {K_GENERATE} genuinely different "
            "approaches (different strategies, not rephrasings), each as a "
            "compact plan. Reply as a JSON array of strings.",
            parse=parse_thoughts,
        )
        for i, thought in enumerate(approaches):
            vertices[f"g{i}"] = thought
            edges.append(("root", "generate", f"g{i}"))

        # score + keep-best(2).
        numbered = "\n".join(
            f"--- thought {i + 1} ---\n{t}" for i, t in enumerate(approaches)
        )
        scores = await scorer.ask(
            f"Task: {task}\n\nCandidate thoughts:\n{numbered}\n\nScore each "
            "0-10 for how promising it is. Reply as JSON: "
            f'{{"scores": [<{len(approaches)} numbers>]}}',
            parse=parse_scores(len(approaches)),
        )
        ranked = sorted(range(len(approaches)), key=lambda i: -scores[i])
        kept = ranked[:KEEP_BEST]
        print("scores:", ", ".join(f"g{i}={scores[i]:.1f}" for i in range(len(scores))))

        # aggregate: merge the survivors into one thought — the operation
        # that makes it a graph rather than a tree.
        merged = await merger.ask(
            f"Task: {task}\n\nTwo strong partial plans:\n\n"
            + "\n\n".join(f"Plan {n + 1}:\n{approaches[i]}" for n, i in enumerate(kept))
            + "\n\nAggregate them into ONE plan that keeps each one's "
            "strengths and drops the weaknesses. Reply as a single JSON string.",
            parse=parse_text,
        )
        vertices["agg"] = merged
        for i in kept:
            edges.append((f"g{i}", "aggregate", "agg"))

        # refine: one self-loop improvement pass on the aggregate.
        refined = await generator.ask(
            f"Task: {task}\n\nCurrent plan:\n{merged}\n\nRefine it: fix "
            "gaps, tighten ordering, remove redundancy. Reply as a single "
            "JSON string.",
            parse=parse_text,
        )
        vertices["ref"] = refined
        edges.append(("agg", "refine", "ref"))

        # final score: did the graph improve on its best branch?
        final_scores = await scorer.ask(
            f"Task: {task}\n\nThought A:\n{approaches[kept[0]]}\n\n"
            f"Thought B:\n{refined}\n\nScore each 0-10. Reply as JSON: "
            '{"scores": [<2 numbers>]}',
            parse=parse_scores(2),
        )
        await c.note(
            f"graph-of-thoughts: best branch {final_scores[0]:.1f} vs "
            f"aggregated+refined {final_scores[1]:.1f}"
        )
        print("\nexecuted DAG:")
        for src, op, dst in edges:
            print(f"  {src} --{op}--> {dst}")
        print(f"\nfinal plan (scored {final_scores[1]:.1f}/10 vs best branch "
              f"{final_scores[0]:.1f}/10):\n{refined}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
