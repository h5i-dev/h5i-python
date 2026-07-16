# Paper scores

Reference implementations of forty published multi-agent workflows, each
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
| [`self_debugging.py`](self_debugging.py) | Self-Debug ([arXiv:2304.05128](https://arxiv.org/abs/2304.05128)) | rubber-duck: explain your own code line by line before revising against the failure. |
| [`constitutional_ai.py`](constitutional_ai.py) | Constitutional AI ([arXiv:2212.08073](https://arxiv.org/abs/2212.08073)) | per-principle critiques of a draft against an explicit constitution, folded into each revision. |

## Sampling and voting

| Score | Paper | The loop on h5i |
|---|---|---|
| [`self_consistency.py`](self_consistency.py) | Self-Consistency ([arXiv:2203.11171](https://arxiv.org/abs/2203.11171)) | N independent seats reason in parallel; majority vote marginalizes the chains. |
| [`agent_forest.py`](agent_forest.py) | More Agents Is All You Need ([arXiv:2402.05120](https://arxiv.org/abs/2402.05120)) | sampling-and-voting, with the scaling curve re-voted over prefixes of one sample set. |
| [`universal_self_consistency.py`](universal_self_consistency.py) | Universal Self-Consistency ([arXiv:2311.17311](https://arxiv.org/abs/2311.17311)) | free-form voting: a selector `ask` picks the sample most consistent with the population. |

## Debate and consensus

| Score | Paper | The loop on h5i |
|---|---|---|
| [`multiagent_debate.py`](multiagent_debate.py) | Multiagent Debate ([arXiv:2305.14325](https://arxiv.org/abs/2305.14325)) | answer independently → read the others → update, for R rounds; majority at the end. |
| [`mad_divergent.py`](mad_divergent.py) | MAD ([arXiv:2305.19118](https://arxiv.org/abs/2305.19118)) | an obligated-to-disagree negative side vs. affirmative, judged adaptively each round. |
| [`reconcile.py`](reconcile.py) | ReConcile ([arXiv:2309.13007](https://arxiv.org/abs/2309.13007)) | model-diverse round table; explanations shared each round; confidence-weighted vote. |
| [`persuasive_debate.py`](persuasive_debate.py) | Persuasive Debate ([arXiv:2402.06782](https://arxiv.org/abs/2402.06782)) | debaters argue *assigned* sides; a transcript-only judge decides — naive vs. informed judgment in one run. |
| [`negotiation.py`](negotiation.py) | Negotiation Self-Play ([arXiv:2305.10142](https://arxiv.org/abs/2305.10142)) | buyer/seller bargaining games; a critic's notes carry into the next game as in-context learning. |

## Verification and judging of sealed candidates

| Score | Paper | The loop on h5i |
|---|---|---|
| [`chateval.py`](chateval.py) | ChatEval ([arXiv:2308.07201](https://arxiv.org/abs/2308.07201)) | persona judges score one-by-one with the running transcript threaded through; `mean_score_verdict` over the debated ballots. |
| [`mav_bon.py`](mav_bon.py) | Multi-Agent Verification ([arXiv:2502.20379](https://arxiv.org/abs/2502.20379)) | best-of-n candidates × m binary aspect verifiers over recorded evidence; most approvals wins as a verdict policy. |
| [`chain_of_verification.py`](chain_of_verification.py) | CoVe ([arXiv:2309.11495](https://arxiv.org/abs/2309.11495)) | draft → verification questions answered by seats that never saw the draft (factored) → revise. |
| [`selfcheckgpt.py`](selfcheckgpt.py) | SelfCheckGPT ([arXiv:2303.08896](https://arxiv.org/abs/2303.08896)) | per-sentence support of a primary answer checked against N independent samples; low-support flagged. |
| [`prd_peer_rank.py`](prd_peer_rank.py) | PRD ([arXiv:2307.02762](https://arxiv.org/abs/2307.02762)) | contestants judge every answer pair both ways; reviewer weight = agreement with the aggregate; discussion settles the top pair. |

## Ensembling generations

| Score | Paper | The loop on h5i |
|---|---|---|
| [`llm_blender.py`](llm_blender.py) | LLM-Blender ([arXiv:2306.02561](https://arxiv.org/abs/2306.02561)) | pairwise ranking (both presentation orders, position-bias-proof) → generative fusion of the top-k. |
| [`mixture_of_agents.py`](mixture_of_agents.py) | Mixture-of-Agents ([arXiv:2406.04692](https://arxiv.org/abs/2406.04692)) | layered proposers, each fed the whole previous layer; a final aggregator synthesizes. |

## Search, long context, and writing

| Score | Paper | The loop on h5i |
|---|---|---|
| [`tree_of_thoughts.py`](tree_of_thoughts.py) | Tree of Thoughts ([arXiv:2305.10601](https://arxiv.org/abs/2305.10601)) | beam-searched plan tree on cheap `ask` turns; only the best leaf pays for a work turn. |
| [`graph_of_thoughts.py`](graph_of_thoughts.py) | Graph of Thoughts ([arXiv:2308.09687](https://arxiv.org/abs/2308.09687)) | generate/score/keep-best plus *aggregate* and *refine* on an explicit DAG the score prints. |
| [`lats.py`](lats.py) | LATS ([arXiv:2310.04406](https://arxiv.org/abs/2310.04406)) | MCTS where expansion is a revise turn, reward blends `verify` with an LLM value, and failures leave reflections. |
| [`least_to_most.py`](least_to_most.py) | Least-to-Most ([arXiv:2205.10625](https://arxiv.org/abs/2205.10625)) | decompose easiest-first, then solve in order with every prior Q/A in the prompt. |
| [`skeleton_of_thought.py`](skeleton_of_thought.py) | Skeleton-of-Thought ([arXiv:2307.15337](https://arxiv.org/abs/2307.15337)) | skeleton `ask`, then all points expanded in one cross-seat `gather` and stitched in order. |
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
| [`codet.py`](codet.py) | CodeT ([arXiv:2207.10397](https://arxiv.org/abs/2207.10397)) | n blind solutions × an independent test suite; rank by dual execution agreement as a verdict policy. |
| [`alphacodium.py`](alphacodium.py) | AlphaCodium ([arXiv:2401.08500](https://arxiv.org/abs/2401.08500)) | flow engineering: structured problem reflection → AI-generated extra tests → code → iterate until all green. |
| [`agentless.py`](agentless.py) | Agentless ([arXiv:2407.01489](https://arxiv.org/abs/2407.01489)) | fixed pipeline: hierarchical localization over a journaled repo tree → minimal repair → validation. |
| [`parsel.py`](parsel.py) | Parsel ([arXiv:2212.10561](https://arxiv.org/abs/2212.10561)) | decompose into a function graph, implement each spec via `map_reduce`, compose and test the whole. |

## Team topology & self-organization

| Score | Paper | The loop on h5i |
|---|---|---|
| [`exchange_of_thought.py`](exchange_of_thought.py) | Exchange-of-Thought ([arXiv:2312.01823](https://arxiv.org/abs/2312.01823)) | Memory/Report/Relay/Debate topologies as a who-sees-what function; confidence-based termination. |
| [`dylan.py`](dylan.py) | DyLAN ([arXiv:2310.02170](https://arxiv.org/abs/2310.02170)) | a ranker scores contributions each round and the weakest seat is deactivated — the roster is mutable Python state. |
| [`agentverse.py`](agentverse.py) | AgentVerse ([arXiv:2308.10848](https://arxiv.org/abs/2308.10848)) | recruit → collaborate → evaluate → re-recruit, hiring genuinely fresh seats mid-run (a pure-`ask` score never freezes). |
| [`meta_prompting.py`](meta_prompting.py) | Meta-Prompting ([arXiv:2401.12954](https://arxiv.org/abs/2401.12954)) | a conductor invents expert personas on the fly and consults clean seats that see only its instructions. |

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
5. Batch-2 siblings extend each family: `self_debugging`/`constitutional_ai`
   add new feedback sources to the refine loops; `universal_self_consistency`
   frees the vote from exact matching; `chain_of_verification`/`selfcheckgpt`
   turn sampling into fact-checking; `graph_of_thoughts` → `lats` deepen the
   search family; `codet`/`alphacodium`/`agentless`/`parsel` complete the
   codegen tier; and the topology group (`exchange_of_thought`, `dylan`,
   `agentverse`, `meta_prompting`) makes team structure itself the variable.

None of these scores use privileged API — where one is close to what you
need, copy it and edit (see the parent README's note on forking patterns).
