# Example scores

Every example is a complete, resumable score: kill it at any point and run it
again — journaled steps replay and the run continues where it stopped. They
assume agent runtimes are available (`launcher="resident"` brings tmux
sessions up itself; drop it if you park resident sessions yourself, or use
`launcher="herdr"` to bring seats up as [herdr](https://herdr.dev) panes
instead — no tmux needed).

You don't need to `tmux attach` by hand to watch the agents: a resident-launcher
score auto-opens a viewer on each agent session as it comes up — a window
linked into your current tmux session if you run the score inside tmux, a
Windows Terminal tab under WSL, or a new GUI terminal window otherwise. In a
headless shell it prints the exact `tmux attach -t …` command instead. It also
warns when an agent has a turn in flight but its session never appeared or died
mid-turn (with the `h5i env shell … -- true` command to diagnose why). Pass
`watch=False` to `Conductor` to disable it, or set a custom terminal with
`watch="kitty -e tmux attach -t {session}"` / `$H5I_TERMINAL`.

## Running the examples

You need five things:

1. **The SDK** — from the repo root: `pip install -e .` (Python ≥ 3.10).
2. **The engine** — the `h5i` binary on `PATH` (`cargo install --path <h5i repo>`),
   or point `$H5I` at it, or pass `h5i_bin=...` to `Conductor`.
3. **Agent runtime CLIs** — every score hires `runtime="claude"` (Claude Code);
   most also hire `runtime="codex"`. Both CLIs must be installed and logged in.
   `launcher="resident"` additionally needs `tmux` (it spawns the sessions);
   `launcher="herdr"` needs the `herdr` binary and a running herdr session.
4. **A repo to work on** — each score opens `Conductor(".", …)`, so run it from
   the repository the agents should modify, with a **clean worktree** (the
   arena and ensemble scores call `preflight(clean_worktree=True)` and fail
   fast otherwise).
5. **A host that can enforce the `supervised` sandbox tier** — every example
   pins `isolation="supervised"` on the `Conductor`, so hired agents run in
   supervised envs (seccomp-gated, network-jailed) rather than whatever tier
   the host happens to auto-pick. The tier is fail-closed: on a host that
   cannot enforce it, hire errors instead of silently downgrading — drop the
   `isolation=` argument (or set `"auto"`) to fall back to auto-picking.
   Note: a *resumed* run keeps the envs it was created with; changing the
   tier (like changing a model) needs a fresh run id.

`preflight(live=...)` is intended for the default `"attach"` launcher, where
sessions must already be parked on their inboxes. Do not use that check before
the first turn with `launcher="resident"`: resident sessions are started lazily
when a turn is dispatched.

Then run any example as a plain Python script. Every example takes the task
as an optional CLI argument and falls back to the same demo task,
**`implement quicksort with pytest`** — so a bare invocation always works:

```bash
python examples/tutorial/ensemble_score.py                          # demo task
python examples/tutorial/arena_score.py       "implement quicksort with pytest"
python examples/tutorial/review_escalation.py "fix the flaky msg_integration test"
python examples/tutorial/pipeline_score.py
python examples/tutorial/judge_panel_score.py
python examples/tutorial/debate_then_build.py
python examples/tutorial/tournament.py
python examples/tutorial/custom_control_flow.py   # uses the default "attach" launcher:
                                         # park resident sessions yourself first
```

To match the demo task, the scores verify candidates with `pytest -q` — the
quicksort submissions carry their own tests. If you pass a task from another
ecosystem, change the `verify` command in the score too (e.g. back to
`["cargo", "test", "--quiet"]`).

Every example pins inexpensive models instead of inheriting a potentially
costly CLI default: Claude seats use `claude-haiku-4-5` and Codex seats use
`gpt-5.4-mini` with `effort="medium"` (launched as
`-c model_reasoning_effort=medium`, which wins over your `~/.codex/config.toml`
— so a `high` default there won't slow the demos down). Edit the `model=` arguments if your account lacks either model.
Changing a model on an existing run does not rewrite a journaled hire, so also
change the run id (for example, `"ensemble-demo-v2"`) when experimenting with
another model. To resume an interrupted run without configuration changes,
just re-run the same command — each script fixes its run id (`"arena-demo"`,
`"pipeline-demo"`, …) and the journal replays completed steps. Scores that end
in an `apply` pause at a durable human gate: the question is delivered over
`h5i msg`, so answer it from the inbox (`h5i msg inbox`, then `h5i msg ack <n>`
/ `h5i msg reply <n> …`) before the winner touches your worktree.

## One pattern each

| Example | Pattern | When to reach for it |
|---|---|---|
| [`ensemble_score.py`](tutorial/ensemble_score.py) | `ensemble` | Consensus: independent attempts, mutual review/revise, verify, verdict, gated apply. |
| [`arena_score.py`](tutorial/arena_score.py) | `arena` | Competition: best of N independent tries, ranked by neutral verification + smallest diff. |
| [`pipeline_score.py`](tutorial/pipeline_score.py) | `pipeline` | Assembly line: architect → implementer → hardener, each stage fed the last stage's artifact. |
| [`judge_panel_score.py`](tutorial/judge_panel_score.py) | `judge_panel` | Judgment beyond tests: LLM judges score sealed candidates against a rubric, citing recorded evidence. |
| [`debate_then_build.py`](tutorial/debate_then_build.py) | `debate` | Decide before building: argue a design question, then let the conclusion steer real work turns. |

## Composed control flow (the define-by-run payoff)

| Example | Shows |
|---|---|
| [`custom_control_flow.py`](tutorial/custom_control_flow.py) | `ask` data turns feeding `if`, journaled `step`/`scope` effects, dynamic `map_reduce` fan-out (`integrate` under the hood), `patched` mid-run migration, a custom verdict policy as a plain function. |
| [`review_escalation.py`](tutorial/review_escalation.py) | An escalation ladder: cheap model first, senior review loop, senior takeover with the junior's artifact as material. Three workflow-node-types' worth of logic in one `for` and one `if`. |
| [`tournament.py`](tutorial/tournament.py) | Multi-run orchestration: a bracket of arena matches, semifinals in parallel — Conductors are just objects, so composing *runs* is composing function calls. |

None of the pattern functions are privileged — each is ~40 lines of the same
public SDK these examples use (`src/h5i/orchestra/patterns.py`). When a
pattern almost fits, copy it into your score and edit it.

## Paper scores

[`papers/`](papers/README.md) holds reference implementations of forty
published multi-agent workflows — Self-Refine, Reflexion, Tree of Thoughts,
Mixture-of-Agents, MetaGPT, ChatDev, LATS, AgentVerse, and more — each
paper's core loop expressed as an ordinary score over the same public SDK. Same prerequisites
as above; see that README for the map from paper to primitives.
