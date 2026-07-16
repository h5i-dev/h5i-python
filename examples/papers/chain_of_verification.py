"""Chain-of-Verification Reduces Hallucination in Large Language Models
(Dhuliawala et al. 2023, arXiv:2309.11495) — draft, verify factored,
revise.

CoVe's four steps: draft an answer; plan verification questions that would
expose its errors; answer those questions *independently of the draft* so
its hallucinations cannot leak into the checks (the paper's best-performing
"factored" variant); then revise the draft against the evidence. h5i's
seat isolation gives the factored property for free: the verification
questions are answered by seats that never saw the draft.

    python examples/papers/chain_of_verification.py ["<question>"]
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Agent, Conductor

DEMO_QUESTION = (
    "Name three programming languages that had garbage collection before "
    "1980, with the year each first appeared."
)
MAX_CHECKS = 4


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def parse_questions(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("reply must be a non-empty JSON array of question strings")
    return [str(q).strip() for q in value][:MAX_CHECKS]


async def main(question: str) -> None:
    async with Conductor(".", "cove-demo", launcher="resident", isolation="supervised") as c:
        drafter = await c.hire("drafter", runtime="claude", model="claude-haiku-4-5")
        checkers = [
            await c.hire(f"checker{i}", runtime="claude", model="claude-haiku-4-5")
            for i in range(2)
        ]

        # 1. Baseline draft.
        draft = await drafter.ask(
            f"{question}\n\nReply as a single JSON string.", parse=parse_text
        )
        print(f"draft:\n{draft}\n")

        # 2. Plan verification questions targeting the draft's claims.
        checks = await drafter.ask(
            f"Question: {question}\nDraft answer:\n{draft}\n\n"
            f"Plan at most {MAX_CHECKS} verification questions that would "
            "expose factual errors in this draft — one independent, "
            "self-contained question per claim. Reply as a JSON array of "
            "strings.",
            parse=parse_questions,
        )

        # 3. Execute verifications FACTORED: checker seats never saw the
        # draft, so its errors cannot leak into the evidence. Parallel
        # across seats, sequential within one.
        assignments: dict[str, tuple[Agent, list[int]]] = {}
        for i in range(len(checks)):
            checker = checkers[i % len(checkers)]
            assignments.setdefault(checker.id, (checker, []))[1].append(i)

        async def answer_checks(checker: Agent, indices: list[int]) -> list[tuple[int, str]]:
            return [
                (
                    i,
                    await checker.ask(
                        f"{checks[i]}\n\nAnswer factually and concisely. "
                        "Reply as a single JSON string.",
                        parse=parse_text,
                    ),
                )
                for i in indices
            ]

        groups = await asyncio.gather(
            *(answer_checks(chk, idx) for chk, idx in assignments.values())
        )
        evidence = dict(pair for group in groups for pair in group)
        for i, q in enumerate(checks):
            print(f"check: {q}\n  → {evidence[i]}")

        # 4. Revise the draft against the independent evidence.
        final = await drafter.ask(
            f"Question: {question}\nYour draft:\n{draft}\n\n"
            "Independent verification results:\n"
            + "".join(f"Q: {q}\nA: {evidence[i]}\n" for i, q in enumerate(checks))
            + "\nRewrite the answer, keeping only claims the evidence "
            "supports and correcting the rest. Reply as a single JSON string.",
            parse=parse_text,
        )
        await c.note(f"chain-of-verification: {len(checks)} factored checks")
        print(f"\nverified answer:\n{final}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_QUESTION))
