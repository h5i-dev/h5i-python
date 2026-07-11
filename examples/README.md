# Example scores

Every example is a complete, resumable score: kill it at any point and run it
again — journaled steps replay and the run continues where it stopped. They
assume agent runtimes are available (`launcher="resident"` brings tmux
sessions up itself; drop it if you park resident sessions yourself).

## Running the examples

You need four things:

1. **The SDK** — from the repo root: `pip install -e .` (Python ≥ 3.10).
2. **The engine** — the `h5i` binary on `PATH` (`cargo install --path <h5i repo>`),
   or point `$H5I` at it, or pass `h5i_bin=...` to `Conductor`.
3. **Agent runtime CLIs** — every score hires `runtime="claude"` (Claude Code);
   most also hire `runtime="codex"`. Both CLIs must be installed and logged in.
   `launcher="resident"` additionally needs `tmux` (it spawns the sessions).
4. **A repo to work on** — each score opens `Conductor(".", …)`, so run it from
   the repository the agents should modify, with a **clean worktree** (the
   arena and ensemble scores call `preflight(clean_worktree=True)` and fail
   fast otherwise).

`preflight(live=...)` is intended for the default `"attach"` launcher, where
sessions must already be parked on their inboxes. Do not use that check before
the first turn with `launcher="resident"`: resident sessions are started lazily
when a turn is dispatched.

Then run any example as a plain Python script. Three take the task as an
optional CLI argument (falling back to a demo task):

```bash
python examples/ensemble_score.py    "implement quicksort"
python examples/arena_score.py       "implement quicksort"
python examples/review_escalation.py "implement quicksort"
```

The rest are self-contained — the task is written into the score:

```bash
python examples/pipeline_score.py
python examples/judge_panel_score.py
python examples/debate_then_build.py
python examples/tournament.py
python examples/custom_control_flow.py   # uses the default "attach" launcher:
                                         # park resident sessions yourself first
```

Model coverage varies: `arena_score.py` and `review_escalation.py` hire
`claude-haiku-4-5`, and `judge_panel_score.py`, `review_escalation.py`, and
`tournament.py` hire `claude-opus-4-8` — edit the `model=` arguments if your
account lacks a model. To resume an interrupted run, just re-run the same
command — each script fixes its run id (`"arena-demo"`, `"pipeline-demo"`, …)
and the journal replays completed steps. Scores that end in an `apply` pause
at a durable human gate: the question is delivered over `h5i msg`, so answer
it from the inbox (`h5i msg inbox`, then `h5i msg ack <n>` / `h5i msg reply
<n> …`) before the winner touches your worktree.

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
