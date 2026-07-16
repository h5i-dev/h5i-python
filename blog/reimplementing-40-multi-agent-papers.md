# I Re-Implemented 40 Multi-Agent LLM Papers. Here's What They Have in Common.

I recently re-implemented the core workflow of 40 published multi-agent
LLM papers — Reflexion, Tree of Thoughts, MetaGPT, ChatDev, LATS,
Mixture-of-Agents, Constitutional AI, and 33 more — as runnable reference
scripts on [h5i](https://github.com/h5i-dev/h5i-python), a small
define-by-run orchestration SDK I work on. Every implementation lives in
[`examples/papers/`](https://github.com/h5i-dev/h5i-python/tree/main/examples/papers),
one file per paper, 50–160 lines each (4,100 lines all told).

Two ground rules made this tractable, and they shape everything below:

1. **Reproduce the workflow, not the experiments.** Each script expresses
   the paper's algorithm — the loop, the roles, the aggregation rule — and
   stays generic over the task you pass it. I make no benchmark claims.
2. **No privileged machinery.** Everything is built from the SDK's public
   surface: six agent-turn primitives (`work`, `ask`, `review`, `revise`,
   plus conductor-level `verify` and `judge`), a `freeze` operation that
   seals a round against cross-agent influence, and plain `asyncio`.

That second rule turned the project into an accidental survey: if 40
papers can be expressed with six primitives and ordinary Python control
flow, the interesting question is no longer "how do I implement paper X"
but "what do these papers actually consist of."

## The corpus

Grouped by family (arXiv IDs in the repo README, linked per file):

- **Refine loops** — Self-Refine, Reflexion, CRITIC, Self-Debug,
  Constitutional AI
- **Sampling and voting** — Self-Consistency, More Agents Is All You Need,
  Universal Self-Consistency
- **Debate and consensus** — Multiagent Debate (Du et al.), MAD divergent
  thinking, ReConcile, persuasive assigned-side debate, negotiation
  self-play
- **Judging and evaluation** — ChatEval, Multi-Agent Verification
  (BoN-MAV), Chain-of-Verification, SelfCheckGPT, PRD peer rank
- **Ensembling** — LLM-Blender, Mixture-of-Agents
- **Search and planning** — Tree of Thoughts, Graph of Thoughts, LATS,
  Least-to-Most, Skeleton-of-Thought, Meta-Prompting
- **Long context and writing** — Chain of Agents, STORM, CAMEL
- **Software-engineering pipelines** — AgentCoder, MapCoder, MetaGPT,
  ChatDev, CodeT, AlphaCodium, Agentless, Parsel
- **Team topology and self-organization** — Exchange-of-Thought, DyLAN,
  AgentVerse

Here is what re-implementing all of them taught me.

## 1. Most of these papers are ~100 lines of control flow

Strip away the evaluation sections and the framework advertising, and the
median paper's contribution is: a loop shape, a prompt discipline, and an
aggregation rule. Multiagent debate is "answer independently, then read
the others and update, then vote" — about 90 lines including argument
parsing. Skeleton-of-Thought is one planning call and one parallel gather
— 80 lines. Even MetaGPT's standard-operating-procedure, once you have a
`work` primitive and typed documents, is a hundred lines.

This is not a criticism. Small algorithms with real effects are the best
kind. But it changed how I read new agent papers: I now look for the loop
shape and the aggregation rule first, and I'm suspicious when a paper
can't be summarized that way.

## 2. Independence is the load-bearing invariant

A surprising number of papers silently depend on samples being
*independent*: self-consistency's vote is meaningless if the samples saw
each other; CodeT's "dual execution agreement" requires tests written
blind to the implementations; Chain-of-Verification's best variant
("factored") requires the verification questions to be answered by a
context that never saw the draft — precisely so the draft's hallucinations
can't leak into the checks.

In single-context frameworks this invariant is easy to break by accident:
one shared history and your five "independent samples" are five
paraphrases. Having isolation as an *enforced* property — separate agent
sessions, plus a `freeze` barrier and an `expect_independent` flag that
fails loudly if an artifact was influenced — meant several papers' central
mechanisms fell out for free. The factored CoVe variant, the hardest one
in the paper, was the *easiest* to implement: just answer the questions on
seats that never saw the draft.

If you build agent infrastructure, make independence a first-class,
checkable property. It's the invariant the most robust methods lean on.

## 3. The refine-loop family is one loop with different feedback sources

Self-Refine, Reflexion, CRITIC, Self-Debug, and Constitutional AI are the
same two-step loop — attempt, then revise against feedback — and differ
*only* in where the feedback comes from:

| Paper | Feedback source |
|---|---|
| Self-Refine | the same model, critiquing |
| Reflexion | the model's own reflection on a failure signal |
| CRITIC | external tool output |
| Self-Debug | the model explaining its own code line by line |
| Constitutional AI | critiques against written principles |

Implementation-wise, the useful move was making feedback a first-class
object: whatever its source, it becomes a structured review the agent
revises against, and every retry is a recorded turn. Once feedback is an
object, the five papers are one function with a parameter.

The rubber-duck detail in Self-Debug is worth stealing: before fixing,
the model must explain what its code *actually does*, not what it was
meant to do. In my (anecdotal, cheap-model) runs this produced noticeably
more targeted revisions than passing the error message alone.

## 4. Prefer execution over opinion, and never verify in the author's environment

The methods that hold up best replace an LLM's opinion with a real signal
wherever one exists: CRITIC runs tools, AgentCoder runs tests, LATS uses
execution results as its search reward, CodeT ranks candidates by whether
they pass a blind test suite. The LLM-judge papers themselves are mostly
about *compensating* for the absence of such a signal — with persona
diversity (ChatEval), verifier count (Multi-Agent Verification), or peer
weighting (PRD).

One engineering detail matters more than it looks: verification has to be
a *neutral re-execution* — apply the candidate to a fresh sandbox and run
the command there — never "the agent says its tests pass." Every
test-driven paper (AgentCoder, CodeT, AlphaCodium, MapCoder) assumes this
property, usually implicitly.

## 5. Aggregation rules are ten lines and decide everything

Majority vote, confidence-weighted vote (ReConcile), mean-of-judges
(ChatEval), approval counting across aspect verifiers (BoN-MAV), win
counts over pairwise comparisons (LLM-Blender), dual execution agreement
(CodeT): each is about ten lines of host-language code, and each is the
actual difference between papers that otherwise share a skeleton.

Two practical notes. First, pairwise comparison beats absolute scoring,
but only if you present each pair in *both orders* and count a win only
when it survives the swap — position bias is real and this is the cheap
fix (LLM-Blender and PRD both need it). Second, keep the aggregation in
ordinary code, not in a prompt. It's the part you'll want to unit test.

## 6. The debate family is a visibility function

Multiagent debate, MAD, ReConcile, and Exchange-of-Thought differ mainly
in *who sees whose messages between rounds*. EoT makes this explicit with
four topologies, and the entire difference fits in one function:

```python
def visible_peers(topology: str, me: int, n: int) -> list[int]:
    if topology == "memory":   # bus: everyone
        return [j for j in range(n) if j != me]
    if topology == "report":   # star: spokes <-> hub
        return [j for j in range(n) if j != me] if me == 0 else [0]
    if topology == "relay":    # ring: predecessor only
        return [(me - 1) % n]
    if topology == "debate":   # tree: siblings pair, root hears all
        return [j for j in range(n) if j != me] if me == 0 else [me % 2 + 1]
```

Everything else — the rounds, the update prompt, the final vote — is
shared. Add a stopping rule (unanimity, judge ruling, or confidence
streaks) and an aggregation rule, and you can generate most of the debate
literature by picking one item from each column.

## 7. Dynamic team structure needs mutable state, not a workflow graph

Two papers were the strongest argument for define-by-run orchestration
over static workflow graphs. DyLAN prunes the team as it goes — a ranker
scores each round's contributions and the weakest agent is deactivated,
which in code is literally `active.remove(weakest)`. AgentVerse goes
further: an evaluator can reject the result, dissolve the team, and
*recruit a differently-shaped one*, which requires hiring new agents
mid-run based on LLM output.

Neither fits a DAG you compile up front, because the *structure* is
computed by the workflow itself. In plain Python both were trivial.

## 8. Search over thoughts is cheap; search over attempts is not

Tree of Thoughts, Graph of Thoughts, and LATS form a cost ladder. ToT and
GoT search over *text* — proposing and scoring thoughts are cheap data
turns, and only the winning plan pays for real implementation work. LATS
searches over *actual attempts*, where every tree node is a real
submission plus a real test run. That's an order of magnitude more
expensive per node, and it buys you a reward signal that isn't an opinion.

The practical recipe that emerged: search broad over text, commit narrow
over execution. ToT-style planning to pick a direction, then a LATS-style
loop only on the final candidate.

## 9. Validate at the turn boundary

Every structured reply in all 40 scripts goes through the same mechanism:
the agent must return JSON, a parser validates it (and checks semantic
constraints — "you scored a candidate that doesn't exist", "your citation
ids aren't in the evidence"), and a failed parse triggers a bounded
re-ask with the error attached. This single pattern eliminated the
majority of flakiness. LLM-judge outputs especially need the semantic
checks: judges *will* cite evidence that doesn't exist, and a validation
loop that rejects hallucinated citations is cheap insurance.

## 10. Forty papers is really about eight papers

The honest meta-lesson. When I selected the second batch of 20, the
hardest part was finding papers that weren't already implied by the first
batch. Several well-cited works reduce to compositions of others: a
review-cycle plus a judge panel covers whole "author/reviewer/meta-
reviewer" frameworks; the EoT topology function subsumes the
communication-topology papers; multi-persona single-model methods are the
role-playing papers with fewer sessions.

Again, not a dig — consolidation is what a healthy field looks like from
inside. But if you're building products rather than publishing: implement
the eight families, parameterize them, and you have coverage of most of
the literature. The families, roughly: refine loops, sample-and-vote,
debate-with-a-visibility-function, judge panels, generative fusion,
text-search-then-commit, staged pipelines (software and long-form
writing), and dynamic team management.

## What didn't map

For fairness, the categories I deliberately excluded: anything requiring
training or weight access (RLHF-style methods, learned rankers — I
implemented LLM-Blender's PairRanker as a prompted judge instead),
methods needing token-level logits, environment-heavy simulations
(Generative Agents), and the workflow-*search* meta-papers (AFlow, ADAS,
GPTSwarm) — those treat everything above as their search space and are
projects in themselves, not afternoon scripts.

Also, one honest engineering caveat: two paper mechanics needed
workarounds. Self-Refine wants a model to review its own artifact, which
the engine forbids for provenance reasons (solved: a second seat pinned
to the same model). And CodeT wants per-test granularity where my
verifier reports per-suite (solved: coarser agreement, noted in the
docstring). Everything else mapped without friction.

## Closing

All 40 scripts are in the repo, each one self-contained, cheap-model
pinned, and generic over the task you pass it:
[github.com/h5i-dev/h5i-python](https://github.com/h5i-dev/h5i-python) —
see `examples/papers/`. If you re-implement a paper I missed, or find a
place where my reading of a paper's algorithm is off, issues and PRs are
welcome.
