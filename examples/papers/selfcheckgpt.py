"""SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for
Generative Large Language Models (Manakul et al. 2023, arXiv:2303.08896) —
consistency across independent samples as a truth signal.

The premise: when a model *knows* a fact, independent samples agree on it;
hallucinations scatter. So: take a primary answer, draw N independent
samples of the same question from separate seats, then have a checker
score each sentence of the primary answer against each sample —
low-support sentences get flagged. No external database, no logits; just
sampling and comparison over journaled ``ask`` turns.

    python examples/papers/selfcheckgpt.py ["<question>"]
"""

import asyncio
import re
import sys
from typing import Any

from h5i.orchestra import Conductor

DEMO_QUESTION = "Give a short factual biography of Alan Turing (4-6 sentences)."
N_SAMPLES = 3
SUPPORT_THRESHOLD = 0.5  # below this mean support, a sentence is flagged


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


def parse_scores(expected: int):
    def parse(value: Any) -> list[float]:
        scores = value.get("scores") if isinstance(value, dict) else value
        if not isinstance(scores, list) or len(scores) != expected:
            raise ValueError(
                f'reply must be {{"scores": [<{expected} numbers, 0=contradicted, '
                "0.5=not mentioned, 1=supported>]}}"
            )
        return [max(0.0, min(1.0, float(s))) for s in scores]

    return parse


def sentences_of(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


async def main(question: str) -> None:
    async with Conductor(".", "selfcheck-demo", launcher="resident", isolation="supervised") as c:
        primary = await c.hire("primary", runtime="claude", model="claude-haiku-4-5")
        samplers = [
            await c.hire(f"sampler{i}", runtime="claude", model="claude-haiku-4-5")
            for i in range(N_SAMPLES)
        ]
        checker = await c.hire("checker", runtime="claude", model="claude-haiku-4-5")

        # The answer under scrutiny + N independent samples, in parallel.
        answer, *samples = await asyncio.gather(
            primary.ask(f"{question}\n\nReply as a single JSON string.", parse=parse_text),
            *(
                s.ask(f"{question}\n\nReply as a single JSON string.", parse=parse_text)
                for s in samplers
            ),
        )
        sentences = sentences_of(answer)
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sentences))

        # Per-sentence support, checked against each sample separately.
        support = [0.0] * len(sentences)
        for sample_no, sample in enumerate(samples, 1):
            scores = await checker.ask(
                "Check each numbered sentence against the reference passage."
                f"\n\nSentences:\n{numbered}\n\nReference passage:\n{sample}\n\n"
                "For each sentence: 1 if the reference supports it, 0 if the "
                "reference contradicts it, 0.5 if the reference does not "
                'mention it. Reply as JSON: {"scores": '
                f"[<{len(sentences)} numbers>]}}",
                parse=parse_scores(len(sentences)),
            )
            support = [acc + s for acc, s in zip(support, scores)]
            print(f"checked against sample {sample_no}/{len(samples)}")

        # Flag the low-consistency sentences.
        flagged = 0
        print("\nannotated answer:")
        for sentence, total in zip(sentences, support):
            mean = total / len(samples)
            mark = " " if mean >= SUPPORT_THRESHOLD else "⚠"
            if mark == "⚠":
                flagged += 1
            print(f" {mark} [{mean:.2f}] {sentence}")
        await c.note(
            f"selfcheckgpt: {flagged}/{len(sentences)} sentences below "
            f"{SUPPORT_THRESHOLD} support across {len(samples)} samples"
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_QUESTION))
