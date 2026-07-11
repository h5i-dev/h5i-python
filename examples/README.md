# Example scores

Every example is a complete, resumable score: kill it at any point and run it
again — journaled steps replay and the run continues where it stopped. They
assume agent runtimes are available (`launcher="resident"` brings tmux
sessions up itself; drop it if you park resident sessions yourself).

## One pattern each

| Example | Pattern | When to reach for it |
|---|---|---|
| [`ensemble_score.py`](ensemble_score.py) | `ensemble` | Consensus: independent attempts, mutual review/revise, verify, verdict, gated apply. |
| [`arena_score.py`](arena_score.py) | `arena` | Competition: best of N independent tries, ranked by neutral verification + smallest diff. |
| [`pipeline_score.py`](pipeline_score.py) | `pipeline` | Assembly line: architect → implementer → hardener, each stage fed the last stage's artifact. |
| [`judge_panel_score.py`](judge_panel_score.py) | `judge_panel` | Judgment beyond tests: LLM judges score sealed candidates against a rubric, citing recorded evidence. |
| [`debate_then_build.py`](debate_then_build.py) | `debate` | Decide before building: argue a design question, then let the conclusion steer real work turns. |

## Composed control flow (the define-by-run payoff)

| Example | Shows |
|---|---|
| [`custom_control_flow.py`](custom_control_flow.py) | `ask` data turns feeding `if`, journaled `step`/`scope` effects, dynamic `map_reduce` fan-out (`integrate` under the hood), `patched` mid-run migration, a custom verdict policy as a plain function. |
| [`review_escalation.py`](review_escalation.py) | An escalation ladder: cheap model first, senior review loop, senior takeover with the junior's artifact as material. Three workflow-node-types' worth of logic in one `for` and one `if`. |
| [`tournament.py`](tournament.py) | Multi-run orchestration: a bracket of arena matches, semifinals in parallel — Conductors are just objects, so composing *runs* is composing function calls. |

None of the pattern functions are privileged — each is ~40 lines of the same
public SDK these examples use (`src/h5i/orchestra/patterns.py`). When a
pattern almost fits, copy it into your score and edit it.
