"""Least-to-Most Prompting Enables Complex Reasoning in Large Language
Models (Zhou et al. 2023, arXiv:2205.10625) — decompose, then solve
easiest-first with accumulated answers.

Two stages: a decomposer reduces the problem to a sequence of simpler
subquestions ordered least-to-most difficult, then a solver answers them
strictly in order, with every prior subquestion *and its answer* riding in
the prompt — so each step only ever bridges a small gap. The sequential
dependency chain is a plain ``for`` loop over journaled ``ask`` turns.

    python examples/papers/least_to_most.py ["<question>"]
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Conductor

DEMO_QUESTION = (
    "Elsa has 5 apples. Anna has 2 more apples than Elsa. Together with "
    "Kristoff's apples the three have 14. How many apples does Kristoff have?"
)
MAX_SUBQUESTIONS = 4


def parse_subquestions(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("reply must be a non-empty JSON array of subquestion strings")
    return [str(q).strip() for q in value][:MAX_SUBQUESTIONS]


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


async def main(question: str) -> None:
    async with Conductor(".", "l2m-demo", launcher="resident", isolation="supervised") as c:
        decomposer = await c.hire("decomposer", runtime="claude", model="claude-haiku-4-5")
        solver = await c.hire("solver", runtime="claude", model="claude-haiku-4-5")

        # Stage 1: decompose, easiest first.
        subquestions = await decomposer.ask(
            f"Problem: {question}\n\nDecompose it into at most "
            f"{MAX_SUBQUESTIONS} subquestions ordered from easiest to "
            "hardest, where each builds on the previous answers and the "
            "last one resolves the original problem. Reply as a JSON array "
            "of strings.",
            parse=parse_subquestions,
        )

        # Stage 2: solve in order; every prior Q/A rides along.
        solved: list[tuple[str, str]] = []
        for i, sub in enumerate(subquestions, 1):
            context = "".join(f"Q: {q}\nA: {a}\n" for q, a in solved)
            answer = await solver.ask(
                f"Original problem: {question}\n\n"
                + (f"Already solved:\n{context}\n" if solved else "")
                + f"Next subquestion: {sub}\n\nAnswer just this subquestion. "
                "Reply as a single JSON string.",
                parse=parse_text,
            )
            solved.append((sub, answer))
            print(f"{i}. {sub}\n   → {answer}")

        final = await solver.ask(
            f"Original problem: {question}\n\nSolved subquestions:\n"
            + "".join(f"Q: {q}\nA: {a}\n" for q, a in solved)
            + "\nState the final answer to the original problem, as short "
            "as possible. Reply as a single JSON string.",
            parse=parse_text,
        )
        await c.note(f"least-to-most: {len(solved)} subquestions → {final}")
        print(f"\nfinal answer: {final}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_QUESTION))
