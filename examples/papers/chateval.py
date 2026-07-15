"""ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate
(Chan et al. 2024, arXiv:2308.07201) — a persona-diverse referee team that
debates before scoring.

A single LLM judge is biased and noisy; ChatEval replaces it with a panel of
*distinct personas* that communicate: in the one-by-one protocol each
evaluator sees what earlier evaluators said before adding its own ballot.
``patterns.judge_panel`` polls its judges independently, so this score opens
the pattern up: same evidence-grounded ``Ballot``s and citation validation,
but the panel speaks in sequence with the running transcript threaded
through, and the mean-score verdict is recorded over the debated ballots.

    python examples/papers/chateval.py ["<task>"]   # default: implement quicksort with pytest
"""

import asyncio
import sys

from h5i.orchestra import Conductor, patterns

DEMO_TASK = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]
PERSONAS = (
    ("critic-correct", "You care only about functional correctness and test rigor."),
    ("critic-clarity", "You care only about readability and maintainability."),
    ("critic-scope", "You care only about scope discipline: no gold-plating, no gaps."),
)


async def main(task: str) -> None:
    async with Conductor(".", "chateval-demo", launcher="resident", isolation="supervised") as c:
        alice = await c.hire("alice", runtime="claude", model="claude-haiku-4-5")
        bob = await c.hire("bob", runtime="codex", model="gpt-5.4-mini", effort="medium")
        panel = [
            await c.hire(name, runtime="claude", model="claude-haiku-4-5")
            for name, _ in PERSONAS
        ]

        # Two candidates to referee: independent attempts, sealed, then
        # neutrally verified so the panel has real evidence to cite.
        a, b = await asyncio.gather(
            alice.work(task, expect_independent=True),
            bob.work(task, expect_independent=True),
        )
        await c.freeze()
        await c.verify(a, VERIFY)
        await c.verify(b, VERIFY)

        status = await c.status()
        candidate_ids = [s.id for s in status.submissions]
        valid_ids = {s.id for s in status.submissions} | {v.id for v in status.verifications}
        evidence = patterns.render_evidence(status)

        # One-by-one communication: each persona reads the prior ballots
        # before casting its own — the debate part of ChatEval.
        transcript: list[str] = []
        ballots: list[patterns.Ballot] = []
        for judge, (_, persona) in zip(panel, PERSONAS):
            heard = (
                "Earlier evaluators said:\n" + "\n".join(transcript)
                if transcript
                else "You speak first."
            )
            prompt = (
                f"You are one evaluator on a referee team. Persona: {persona}\n"
                f"Task under evaluation: {task}\n\n{heard}\n\n"
                "Score EACH candidate 0-10 from your persona's standpoint, "
                "grounding every rationale in the recorded evidence (cite the "
                "exact ids you used). You may rebut earlier evaluators.\n\n"
                f"Candidates: {', '.join(candidate_ids)}\n\nEvidence:\n{evidence}\n\n"
                'Reply as JSON: {"ballots": [{"artifact_id": "<id>", '
                '"score": <0-10>, "rationale": "<why, citing ids>", '
                '"cited_ids": ["<id>", …]}]}.'
            )
            card = await patterns.ask_with_valid_citations(
                judge, prompt, valid_ids, candidate_ids
            )
            ballots.extend(card)
            transcript.extend(
                f"[{judge.id}] {b.artifact_id}: {b.score}/10 — {b.rationale}" for b in card
            )

        # Aggregate the debated ballots with the stock mean-score rule.
        verdict = await c.judge(
            lambda run: patterns.mean_score_verdict(ballots, len(panel), run)
        )
        for line in transcript:
            print(line[:140])
        print("\nverdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_TASK))
