"""Assisting in Writing Wikipedia-like Articles From Scratch with Large
Language Models (Shao et al. 2024, arXiv:2402.14207) — STORM's pre-writing
stage: perspectives → simulated interviews → outline → article.

STORM's insight is that article *quality is decided before writing starts*:
discover the distinct perspectives a topic deserves, then research each one
by simulating a conversation — a curious writer asking pointed questions,
an expert answering — and only then outline and draft. Here each stage is
an ``ask`` data turn: perspectives and the outline are validated JSON, the
interviews are alternating turns between two seats, and every conversation
is journaled, so a killed run resumes mid-interview.

    python examples/papers/storm.py ["<topic>"]
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Conductor

DEMO_TOPIC = "how git stores history internally"
N_PERSPECTIVES = 2
INTERVIEW_TURNS = 2


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def parse_strings(cap: int):
    def parse(value: Any) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("reply must be a non-empty JSON array of strings")
        return [str(s).strip() for s in value][:cap]

    return parse


async def main(topic: str) -> None:
    async with Conductor(".", "storm-demo", launcher="resident", isolation="supervised") as c:
        writer = await c.hire("writer", runtime="claude", model="claude-haiku-4-5")
        expert = await c.hire("expert", runtime="codex", model="gpt-5.4-mini", effort="medium")
        editor = await c.hire("editor", runtime="claude", model="claude-haiku-4-5")

        # 1. Perspective discovery: what distinct angles does this deserve?
        perspectives = await writer.ask(
            f"Topic: {topic}\n\nName {N_PERSPECTIVES} DISTINCT perspectives "
            "an article on this topic should cover (e.g. practitioner, "
            "historian, skeptic — whatever fits this topic). Reply as a JSON "
            "array of short strings.",
            parse=parse_strings(N_PERSPECTIVES),
        )
        print("perspectives:", "; ".join(perspectives))

        # 2. Simulated interviews: per perspective, the writer asks, the
        # expert answers — grounded question asking, the heart of STORM.
        notes: list[str] = []
        for perspective in perspectives:
            dialogue = ""
            for _ in range(INTERVIEW_TURNS):
                question = await writer.ask(
                    f"You research '{topic}' from this perspective: "
                    f"{perspective}.\nConversation so far:\n{dialogue or '(start)'}\n"
                    "Ask the expert your single most informative next "
                    "question — specific, not generic. Reply as a JSON string.",
                    parse=parse_text,
                )
                answer = await expert.ask(
                    f"You are a domain expert on '{topic}'. Answer concisely "
                    f"and concretely:\n{question}\n\nReply as a JSON string.",
                    parse=parse_text,
                )
                dialogue += f"Q: {question}\nA: {answer}\n"
            notes.append(f"[perspective: {perspective}]\n{dialogue}")
            print(f"interviewed for '{perspective}' ({INTERVIEW_TURNS} turns)")

        # 3. Outline from the collected conversations.
        outline = await writer.ask(
            f"Topic: {topic}\n\nInterview notes:\n\n" + "\n\n".join(notes) + "\n\n"
            "Draft the article outline: section titles in reading order. "
            "Reply as a JSON array of strings (max 5).",
            parse=parse_strings(5),
        )
        print("outline:", " / ".join(outline))

        # 4. Write the full article from outline + notes.
        article = await editor.ask(
            f"Write a well-organized article on: {topic}\n\n"
            "Outline:\n" + "\n".join(f"- {s}" for s in outline) + "\n\n"
            "Source notes:\n\n" + "\n\n".join(notes) + "\n\n"
            "Ground every section in the notes. Markdown, one paragraph per "
            "section. Reply as a single JSON string.",
            parse=parse_text,
        )
        await c.note(f"storm: article on '{topic}' from {len(perspectives)} interviews")
        print(f"\n{article}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TOPIC))
