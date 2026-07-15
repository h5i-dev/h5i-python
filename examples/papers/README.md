# Paper scores

Reference implementations of twenty published multi-agent workflows, each
expressed as an ordinary h5i score. The goal is the *core algorithm* of each
paper — the loop, the roles, the aggregation rule — not a reproduction of its
experiments: every score is generic over the task it is given (pass your own
as the CLI argument), and every effectful turn is journaled, so any score can
be killed and re-run to resume where it stopped.

Prerequisites, model pinning, and runtime setup are the same as the parent
[examples/README.md](../README.md). Scores that produce code artifacts default
to the shared demo task (`implement quicksort with pytest`) and verify with
`pytest -q`; scores over questions or instructions are pure `ask` data turns
and need no clean worktree.

## Refine loops (one worker, an external signal)

| Score | Paper | The loop on h5i |
|---|---|---|
| [`self_refine.py`](self_refine.py) | Self-Refine ([arXiv:2303.17651](https://arxiv.org/abs/2303.17651)) | generate → critic seat (same model) reviews → revise, until approved. |
| [`reflexion.py`](reflexion.py) | Reflexion ([arXiv:2303.11366](https://arxiv.org/abs/2303.11366)) | `verify` as the evaluator; verbal reflections accumulate in an episodic buffer delivered as the revise review. |
| [`critic.py`](critic.py) | CRITIC ([arXiv:2305.11738](https://arxiv.org/abs/2305.11738)) | a toolbox of `verify` commands grounds each critique; correct → re-verify. |

## Sampling and voting

| Score | Paper | The loop on h5i |
|---|---|---|
| [`self_consistency.py`](self_consistency.py) | Self-Consistency ([arXiv:2203.11171](https://arxiv.org/abs/2203.11171)) | N independent seats reason in parallel; majority vote marginalizes the chains. |
| [`agent_forest.py`](agent_forest.py) | More Agents Is All You Need ([arXiv:2402.05120](https://arxiv.org/abs/2402.05120)) | sampling-and-voting, with the scaling curve re-voted over prefixes of one sample set. |

## Debate and consensus

| Score | Paper | The loop on h5i |
|---|---|---|
| [`multiagent_debate.py`](multiagent_debate.py) | Multiagent Debate ([arXiv:2305.14325](https://arxiv.org/abs/2305.14325)) | answer independently → read the others → update, for R rounds; majority at the end. |
| [`mad_divergent.py`](mad_divergent.py) | MAD ([arXiv:2305.19118](https://arxiv.org/abs/2305.19118)) | an obligated-to-disagree negative side vs. affirmative, judged adaptively each round. |
| [`reconcile.py`](reconcile.py) | ReConcile ([arXiv:2309.13007](https://arxiv.org/abs/2309.13007)) | model-diverse round table; explanations shared each round; confidence-weighted vote. |

## Verification and judging of sealed candidates

| Score | Paper | The loop on h5i |
|---|---|---|
| [`chateval.py`](chateval.py) | ChatEval ([arXiv:2308.07201](https://arxiv.org/abs/2308.07201)) | persona judges score one-by-one with the running transcript threaded through; `mean_score_verdict` over the debated ballots. |
| [`mav_bon.py`](mav_bon.py) | Multi-Agent Verification ([arXiv:2502.20379](https://arxiv.org/abs/2502.20379)) | best-of-n candidates × m binary aspect verifiers over recorded evidence; most approvals wins as a verdict policy. |

## Ensembling generations

| Score | Paper | The loop on h5i |
|---|---|---|
| [`llm_blender.py`](llm_blender.py) | LLM-Blender ([arXiv:2306.02561](https://arxiv.org/abs/2306.02561)) | pairwise ranking (both presentation orders, position-bias-proof) → generative fusion of the top-k. |
| [`mixture_of_agents.py`](mixture_of_agents.py) | Mixture-of-Agents ([arXiv:2406.04692](https://arxiv.org/abs/2406.04692)) | layered proposers, each fed the whole previous layer; a final aggregator synthesizes. |

## Search, long context, and writing

| Score | Paper | The loop on h5i |
|---|---|---|
| [`tree_of_thoughts.py`](tree_of_thoughts.py) | Tree of Thoughts ([arXiv:2305.10601](https://arxiv.org/abs/2305.10601)) | beam-searched plan tree on cheap `ask` turns; only the best leaf pays for a work turn. |
| [`chain_of_agents.py`](chain_of_agents.py) | Chain of Agents ([arXiv:2406.02818](https://arxiv.org/abs/2406.02818)) | sequential workers rewrite a communication unit chunk by chunk; the manager answers from the final unit alone. |
| [`storm.py`](storm.py) | STORM ([arXiv:2402.14207](https://arxiv.org/abs/2402.14207)) | perspectives → simulated writer↔expert interviews → outline → article. |
| [`camel.py`](camel.py) | CAMEL ([arXiv:2303.17760](https://arxiv.org/abs/2303.17760)) | task specifier, then inception-prompted user/assistant role-play, one instruction at a time. |

## Software-engineering SOPs

| Score | Paper | The loop on h5i |
|---|---|---|
| [`agentcoder.py`](agentcoder.py) | AgentCoder ([arXiv:2312.13010](https://arxiv.org/abs/2312.13010)) | programmer ∥ mutually-blind test designer; suite granted as materials; neutral executor loops failures back. |
| [`mapcoder.py`](mapcoder.py) | MapCoder ([arXiv:2405.11403](https://arxiv.org/abs/2405.11403)) | self-generated exemplars → confidence-ranked plans → code → bounded plan-wise debugging, switching plans when exhausted. |
| [`metagpt.py`](metagpt.py) | MetaGPT ([arXiv:2308.00352](https://arxiv.org/abs/2308.00352)) | roles exchange validated JSON documents (PRD, design, QA report), never free chat. |
| [`chatdev.py`](chatdev.py) | ChatDev ([arXiv:2307.07924](https://arxiv.org/abs/2307.07924)) | a chat chain: every waterfall phase is a two-role dialogue with a settled deliverable. |

## Reading order

The scores share scaffolding and build on each other:

1. `self_refine` → `reflexion` → `critic` — one worker, three feedback sources
   (a critic seat, its own reflections, external tools).
2. `self_consistency` → `agent_forest` → `multiagent_debate` — from voting to
   debating, same parallel-`ask` skeleton.
3. `chateval` and `mav_bon` — two ways to judge sealed candidates beyond
   what `patterns.judge_panel` ships.
4. `agentcoder` → `mapcoder` → `metagpt` → `chatdev` — increasingly structured
   software SOPs over the same `work`/`verify`/`revise` turns.

None of these scores use privileged API — where one is close to what you
need, copy it and edit (see the parent README's note on forking patterns).
