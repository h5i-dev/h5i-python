"""Chain of Agents: Large Language Models Collaborating on Long-Context
Tasks (Zhang et al. 2024, arXiv:2406.02818) — sequential workers passing a
communication unit, then a manager.

Instead of stuffing a long document into one context (lost-in-the-middle)
or retrieving fragments (lost evidence), CoA interleaves reading and
reasoning: the document is chunked, worker agents read one chunk each *in
order*, and each worker rewrites a running "communication unit" — carrying
forward exactly what matters for the query — before passing it on. A
manager who never sees the document answers from the final unit alone. The
source read is a journaled ``step``, so a resume replays the same document
even if the file changed.

    python examples/papers/chain_of_agents.py ["<question>"] [<path>]
    # defaults: summarize README.md of the current repo
"""

import asyncio
import sys
from pathlib import Path

from h5i.orchestra import Conductor

DEMO_QUESTION = "Summarize the key points of this document in five bullet points."
DEMO_PATH = "README.md"
MAX_DOC_CHARS = 24_000  # stay under the journal's inline step cap
CHUNK_CHARS = 4_000


def chunked(text: str) -> list[str]:
    """Split on paragraph boundaries into ~CHUNK_CHARS pieces."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if current and len(current) + len(paragraph) > CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        chunks.append(current)
    return chunks


async def main(question: str, path: str) -> None:
    async with Conductor(".", "coa-demo", launcher="resident", isolation="supervised") as c:
        workers = [
            await c.hire("worker0", runtime="claude", model="claude-haiku-4-5"),
            await c.hire("worker1", runtime="claude", model="claude-haiku-4-5"),
        ]
        manager = await c.hire("manager", runtime="claude", model="claude-haiku-4-5")

        # Journal the source read: a resume replays the exact same document.
        text = await c.step(
            "read-source", lambda: Path(path).read_text(encoding="utf-8")[:MAX_DOC_CHARS]
        )
        chunks = chunked(text)
        print(f"{path}: {len(text)} chars → {len(chunks)} chunk(s)")

        # Worker chain: strictly sequential — each unit depends on the last.
        unit = "(none yet — you read the first segment)"
        for i, chunk in enumerate(chunks):
            unit = await workers[i % len(workers)].ask(
                f"You are worker {i + 1}/{len(chunks)} in a chain reading a "
                f"long document, one segment each.\nQuery: {question}\n\n"
                f"Communication unit from the previous worker:\n{unit}\n\n"
                f"Your segment:\n{chunk}\n\n"
                "Rewrite the communication unit for the next worker: carry "
                "forward everything relevant to the query, integrate new "
                "evidence from your segment, drop what does not matter. "
                "Reply as a single JSON string.",
                parse=lambda v: v if isinstance(v, str) else str(v),
            )

        # The manager answers from the final unit alone — it never sees the
        # document.
        answer = await manager.ask(
            f"Query: {question}\n\nAccumulated evidence from the worker "
            f"chain:\n{unit}\n\nAnswer the query from this evidence only. "
            "Reply as a single JSON string.",
            parse=lambda v: v if isinstance(v, str) else str(v),
        )
        await c.note(f"chain-of-agents over {path} ({len(chunks)} chunks)")
        print(f"\nanswer:\n{answer}")


if __name__ == "__main__":
    asyncio.run(
        main(
            sys.argv[1] if len(sys.argv) > 1 else DEMO_QUESTION,
            sys.argv[2] if len(sys.argv) > 2 else DEMO_PATH,
        )
    )
