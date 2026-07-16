"""Mixture-of-Agents Enhances Large Language Model Capabilities (Wang et
al. 2024, arXiv:2406.04692) — layered proposers feeding an aggregator.

MoA's finding ("collaborativeness"): an LLM produces a better answer when
shown other models' attempts, even attempts from weaker models. So: layer 1
proposers answer independently; each layer-l proposer receives ALL of layer
l-1's answers as auxiliary references and synthesizes an improved one; a
final aggregator fuses the last layer. The same model-diverse seats serve
every proposer layer (the paper reuses models across layers); depth and
width are the two scaling knobs.

    python examples/papers/mixture_of_agents.py ["<instruction>"]
"""

import asyncio
import sys
from typing import Any

from h5i.orchestra import Conductor

DEMO_TASK = (
    "Write a concise design note: how should a small CLI tool store user "
    "credentials safely, and what trade-offs matter?"
)
LAYERS = 2  # proposer layers before the final aggregation


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def referenced(responses: list[str]) -> str:
    return "\n\n".join(f"Reference {i + 1}:\n{r}" for i, r in enumerate(responses))


async def main(task: str) -> None:
    async with Conductor(".", "moa-demo", launcher="resident", isolation="supervised") as c:
        proposers = [
            await c.hire("prop0", runtime="claude", model="claude-haiku-4-5"),
            await c.hire("prop1", runtime="codex", model="gpt-5.4-mini", effort="medium"),
            await c.hire("prop2", runtime="claude", model="claude-haiku-4-5"),
        ]
        aggregator = await c.hire("aggregator", runtime="claude", model="claude-haiku-4-5")

        # Layer 1: independent proposals.
        responses = list(
            await asyncio.gather(
                *(
                    p.ask(f"{task}\n\nReply as a single JSON string.", parse=parse_text)
                    for p in proposers
                )
            )
        )

        # Layers 2..L: every proposer sees ALL previous-layer responses.
        for layer in range(2, LAYERS + 1):
            responses = list(
                await asyncio.gather(
                    *(
                        p.ask(
                            f"{task}\n\nResponses from the previous layer of "
                            f"agents:\n\n{referenced(responses)}\n\n"
                            "Use them as auxiliary references — adopt what is "
                            "right, correct what is wrong — and write your own "
                            "improved response. Reply as a single JSON string.",
                            parse=parse_text,
                        )
                        for p in proposers
                    )
                )
            )
            print(f"layer {layer}: {len(responses)} refined proposals")

        # Final aggregation.
        final = await aggregator.ask(
            f"{task}\n\nCandidate responses from a mixture of agents:\n\n"
            f"{referenced(responses)}\n\n"
            "Aggregate them into the single best response: synthesize, do not "
            "merely select. Reply as a single JSON string.",
            parse=parse_text,
        )
        await c.note(f"mixture-of-agents: {LAYERS} layers × {len(proposers)} proposers")
        print(f"\naggregated answer:\n{final}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
