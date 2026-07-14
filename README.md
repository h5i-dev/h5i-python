# h5i.orchestra — define-by-run agent orchestration for Python

`h5i.orchestra` is the Python SDK for [h5i](https://github.com/Koukyosyumei/h5i)'s
orchestra engine: **a score is an ordinary async Python program**. `if`, `for`
and `asyncio.gather` are the orchestration language; there is no graph builder,
no YAML workflow, no `compile()` step. Every effectful step (an agent turn, a
verification, a verdict) is journaled on the git-backed team event log, so a
killed score resumes by *running the same file again* — completed agent turns
are never re-executed, and never re-paid.

```python
import asyncio
from h5i.orchestra import Conductor

async def main():
    async with Conductor(".", "fix-auth") as c:
        claude = await c.hire("claude", runtime="claude")
        codex = await c.hire("codex", runtime="codex")

        task = "implement `h5i pull` mirroring `h5i push`"
        a, b = await asyncio.gather(claude.work(task), codex.work(task))

        await c.freeze()                       # seal: no cross-influence before this
        await asyncio.gather(codex.review(a), claude.review(b))

        await c.verify(a, ["cargo", "test", "--quiet"])
        await c.verify(b, ["cargo", "test", "--quiet"])

        verdict = await c.judge()              # tests pass → smallest diff wins
        print("winner:", verdict.selected_submission)

asyncio.run(main())
```

## Why it looks like this

The engine's design doc settles the "graph DSL or eDSL?" question with the
PyTorch lesson: frameworks that let users *perform* the computation and quietly
observe it beat frameworks that ask users to *describe* computation to a
smarter executor — on debuggability, host-language control flow, and
learnability. This SDK keeps that bargain end to end:

- **Eager and debuggable.** Every `await` is a real operation happening now.
  Errors are typed Python exceptions raised at the awaiting line of *your*
  code; `pdb`, `print`, and stack traces just work. The DAG (`await c.trace()`)
  is a *view over the journal*, derived after execution — never a prerequisite
  for it.
- **The host language is the API.** Retry loops are `for` loops. Conditional
  escalation is `if`. Fan-out is `asyncio.gather`. A "custom judge" is a
  Python function `(Run) -> Verdict`. An LLM judge is a policy that `ask`s
  inside.
- **Escape hatches, not walls.** `await c.step("label", fn)` journals any
  Python effect exactly-once. The prebuilt patterns (`ensemble`, `arena`,
  `pipeline`, `map_reduce`, `judge_panel`, `debate`) are ~40 lines of public
  SDK each — copy one into your score and edit it; that's the intended
  workflow.
- **Zero dependencies.** Stdlib only (`asyncio` + `json` + `dataclasses`). The
  heavy lifting — sandboxed envs, the journal, turn dispatch, neutral
  verification — lives in the `h5i` binary.

## How it connects

The SDK spawns `h5i orchestra serve` as a **child process** and speaks
line-delimited JSON-RPC over its stdio. Not a daemon: no socket, no port, no
auth surface; the child exits when your script does. One resident process
holds what must live together (the Conductor, the journal's per-label
sequence counters and fail-closed concurrency checks, the turn-wait pollers);
Python holds the control flow. Because the journal is a git ref, the run
survives both processes — and `h5i share push` moves a live run to another
machine, where the same score resumes it.

The protocol is documented in `crates/h5i-orchestra/src/rpc.rs` (h5i repo).
SDK and binary versions are decoupled by an `initialize` handshake with
protocol version + capability flags.

## Install

```bash
pip install h5i-orchestra          # the SDK (Python ≥ 3.10)
cargo install --path <h5i repo>    # the engine (`h5i` on PATH, or set $H5I)
```

## The surface, briefly

```python
async with Conductor(repo, run, launcher="attach", turn_timeout=1800) as c:
    agent  = await c.hire("name", runtime="claude", model=None, profile=None, env=None)
    agents = await c.roster()                 # bind seats enrolled elsewhere

    art    = await agent.work(task, materials=[...], expect_independent=False)
    data   = await agent.ask(prompt, parse=MyShape.from_value)   # JSON data turn
    rev    = await agent.review(art)
    art2   = await agent.revise(art, rev)

    await c.freeze()                          # seal the round (idempotent)
    ver    = await c.verify(art, ["pytest", "-q"], isolation="container")
    v      = await c.judge()                  # built-in policy, or any callable(Run) -> Verdict
    await c.apply(art)                        # verdict-gated; force=True = human pick

    n      = await c.step("fetch", fetch)     # journal any Python effect exactly-once
    ok     = await c.patched("change-id")     # migrate a changed score mid-run
    ans    = await c.gate("ship it?")         # durable human question over h5i msg
    await c.preflight(live=agents, min_isolation="process", clean_worktree=True)
    print(await c.trace())                    # the recorded DAG
```

**Launchers.** How agent turns find a runtime: `"attach"` (default — resident
sessions parked on their inboxes pick turns up), `"resident"` (the bridge
brings up tmux sessions itself), or `on_turn=my_callback` (every turn is
delivered to your Python function — script deterministic agents in tests, or
spawn your own runtimes).

**Sandboxing.** `Conductor(..., isolation="supervised")` sets the run's
default sandbox tier: every `hire` creates its env at that tier unless it
passes its own (`isolation="container"`, or `"auto"` to re-enable
auto-picking). Explicit tiers are fail-closed — hire errors if the host
cannot enforce them, never silently downgrades — and
`preflight(min_isolation=...)` verifies the floor across the whole roster,
which also catches a *resumed* run whose envs were created at a weaker tier.

**Watching resident sessions.** With `launcher="resident"` the score also
auto-opens a viewer on each agent's tmux session as it comes up — a window
linked into your current tmux session, a Windows Terminal tab under WSL, or a
new GUI terminal — so you never hunt for `tmux attach -t …` by hand. Headless
environments just get the attach command printed. Tune it with
`watch="wezterm start -- tmux attach -t {session}"` (or `$H5I_TERMINAL`), or
turn it off with `watch=False`.

**Discipline the journal asks of you** (same as the Rust eDSL): steps that run
concurrently need distinct labels (`c.scope(f"item/{i}").step("fetch", …)` in
parallel loops), and one agent's turns run sequentially — one resident
session per agent. Violations fail closed with a clear error rather than
corrupting resume.

## Patterns

```python
from h5i.orchestra import patterns

out = await patterns.ensemble(c, task, agents, rounds=2, verify=["pytest", "-q"])
out = await patterns.arena(c, task, agents, verify=["pytest", "-q"])
arts = await patterns.pipeline(c, [(architect, "design"), (builder, "implement")])
out = await patterns.map_reduce(c, [(a, t1), (b, t2)], reduce=(merger, "fuse"))
out = await patterns.judge_panel(c, "smallest correct change", judges)
out = await patterns.debate(c, "tabs or spaces?", [pro, con], moderator=mod)
```

[`examples/`](examples/) has a complete, resumable score per pattern, plus
composed ones — an escalation ladder, a debate that steers real work turns,
and a multi-run tournament bracket — indexed in
[`examples/README.md`](examples/README.md).

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/pytest                   # unit suite runs against an in-process mock
H5I=~/path/to/h5i .venv/bin/pytest tests/test_integration.py   # real binary
```

The integration suite mirrors the engine's cross-process acceptance harness:
scripted `sh` subprocesses play the agents inside real `h5i env shell` boxes,
so the whole Python → bridge → box → host path is exercised without an LLM.

## License

Apache-2.0
