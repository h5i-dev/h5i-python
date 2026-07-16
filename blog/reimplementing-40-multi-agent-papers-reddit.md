# Reddit version

Suggested title (r/MachineLearning): **[P] I re-implemented the core
workflow of 40 multi-agent LLM papers (Reflexion, ToT, MetaGPT, LATS,
MoA, ...) — lessons learned**

Alternative (r/LocalLLaMA): **I re-implemented 40 multi-agent workflow
papers as small runnable scripts. Most of them are ~100 lines of control
flow.**

---

I recently re-implemented the core algorithm of 40 multi-agent LLM
papers — Reflexion, Tree of Thoughts, Graph of Thoughts, LATS, MetaGPT,
ChatDev, Mixture-of-Agents, CodeT, Constitutional AI, DyLAN, AgentVerse,
and 29 more — as standalone reference scripts (50–160 lines each) on a
small define-by-run orchestration SDK. Goal was
the *workflow*, not the benchmarks: each script expresses the paper's
loop, roles, and aggregation rule, and stays generic over the task you
give it. No benchmark claims.

Repo: https://github.com/h5i-dev/h5i-python (see `examples/papers/`,
one file per paper, arXiv links in the README)

Lessons that survived 40 implementations:

- **Most papers are a loop shape + a prompt discipline + an aggregation
  rule.** Median implementation was ~100 lines. I now read new agent
  papers by looking for those three things first.
- **Independence is the load-bearing invariant.** Self-consistency,
  CodeT, and CoVe all silently require samples that never saw each
  other. In shared-context frameworks this breaks by accident. With
  enforced isolation, CoVe's "factored" variant (its best one) was the
  *easiest* thing to build.
- **The refine loops are one algorithm.** Self-Refine / Reflexion /
  CRITIC / Self-Debug / Constitutional AI differ only in where feedback
  comes from (a critic, your own reflection, tools, your own code
  walkthrough, written principles). Make feedback a first-class object
  and it's one function with a parameter.
- **Execution beats opinion.** The methods that hold up ground decisions
  in real test runs (CRITIC, AgentCoder, LATS, CodeT). LLM-judge papers
  are mostly compensation strategies for when you don't have that signal.
  And always verify in a fresh sandbox, never "the agent says tests pass."
- **Aggregation rules are ~10 lines and are the actual paper.** Majority
  vote, confidence-weighted vote, mean-of-judges, approval counting,
  pairwise wins. For pairwise judging: present both orders and only count
  wins that survive the swap, or position bias eats your ranking.
- **The debate literature is a visibility function.** Who sees whose
  messages between rounds (bus/star/ring/tree, per Exchange-of-Thought)
  + a stopping rule + a vote. That's the whole design space.
- **Dynamic teams don't fit static workflow graphs.** DyLAN removes the
  weakest agent mid-run (`active.remove(weakest)`); AgentVerse dissolves
  and re-recruits teams based on LLM output. Both are trivial in plain
  Python, impossible in a precompiled DAG.
- **Honest meta-lesson: 40 papers ≈ 8 families.** Refine loops,
  sample-and-vote, debate, judge panels, fusion, search-then-commit,
  staged pipelines (software and long-form writing), dynamic team
  management. Implement those eight, parameterize, and you cover most
  of the literature.

What I excluded: anything needing training/weights, token logits, heavy
simulation environments, and the workflow-search meta-papers (AFlow/ADAS)
— those are projects, not scripts.

Happy to answer questions about any specific paper's mapping.
