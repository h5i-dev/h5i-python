"""Skeleton-of-Thought: Prompting LLMs for Efficient Parallel Generation
(Ning et al. 2024, arXiv:2307.15337) — skeleton first, points expanded in
parallel.

SoT is a latency technique with a quality side-effect: first elicit a
short skeleton of the answer, then expand every point *simultaneously* and
assemble. Sequential decoding of a long answer becomes a handful of short
parallel completions. The h5i mapping is direct: one skeleton ``ask``,
then a cross-seat ``asyncio.gather`` — points are distributed over a seat
pool, parallel across seats and sequential within one (one resident
session per seat) — and host code stitches the answer back in order.

    python examples/papers/skeleton_of_thought.py ["<question>"]
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Agent, Conductor

DEMO_QUESTION = (
    "What are the main trade-offs when choosing between SQL and NoSQL "
    "databases for a new product?"
)
MAX_POINTS = 5


def parse_skeleton(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("reply must be a non-empty JSON array of short point strings")
    return [str(p).strip() for p in value][:MAX_POINTS]


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


async def main(question: str) -> None:
    async with Conductor(".", "sot-demo", launcher="resident", isolation="supervised") as c:
        planner = await c.hire("planner", runtime="claude", model="claude-haiku-4-5")
        writers = [
            await c.hire(f"writer{i}", runtime="claude", model="claude-haiku-4-5")
            for i in range(3)
        ]

        # 1. The skeleton: short points only, no elaboration yet.
        skeleton = await planner.ask(
            f"Question: {question}\n\nWrite ONLY the skeleton of the answer: "
            f"3-{MAX_POINTS} points, each 3-6 words. Reply as a JSON array "
            "of strings.",
            parse=parse_skeleton,
        )
        print("skeleton:", " | ".join(skeleton))

        # 2. Point expansion — the parallel part. Distribute points over
        # the writer pool: parallel across seats, sequential within a seat.
        assignments: dict[str, tuple[Agent, list[int]]] = {}
        for i in range(len(skeleton)):
            writer = writers[i % len(writers)]
            assignments.setdefault(writer.id, (writer, []))[1].append(i)

        async def expand(writer: Agent, indices: list[int]) -> list[tuple[int, str]]:
            out = []
            for i in indices:
                text = await writer.ask(
                    f"Question: {question}\n\nFull skeleton:\n"
                    + "\n".join(f"{n + 1}. {p}" for n, p in enumerate(skeleton))
                    + f"\n\nWrite ONLY the expansion of point {i + 1} "
                    f"('{skeleton[i]}'): 2-3 sentences, no preamble. Reply "
                    "as a single JSON string.",
                    parse=parse_text,
                )
                out.append((i, text))
            return out

        groups = await asyncio.gather(
            *(expand(writer, indices) for writer, indices in assignments.values())
        )

        # 3. Assemble in skeleton order.
        expanded = dict(pair for group in groups for pair in group)
        answer = "\n\n".join(
            f"{i + 1}. {skeleton[i]} — {expanded[i]}" for i in range(len(skeleton))
        )
        await c.note(f"skeleton-of-thought: {len(skeleton)} points expanded in parallel")
        print(f"\n{answer}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_QUESTION))
