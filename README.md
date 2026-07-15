# h5i-python: Python SDK for Programmable Multi-Agent Orchestration

Claude Code, Codex, and other coding agents have different strengths. However, naive multi-agent orchestration such as simply launching several agents in parallel or allowing them to exchange messages does not define a reproducible development process. A real workflow must specify:

- who implements;
- who reviews whom;
- when an agent must revise its work;
- which candidates are independently tested;
- how the winner is selected; and
- when the selected change is applied to the original branch.

`h5i-python` is the Python SDK for the [h5i](https://github.com/h5i-dev/h5i) orchestra engine. This SDK lets you define and execute multi-agent coding workflows across Claude Code, Codex, and other runtimes as ordinary Python programs.

For example, you can:

- ask Claude and Codex to implement the same task independently, have them review and improve each other's work, and select the smallest candidate that passes the tests;
- let Claude Fable and Codex GPT-5.6 Sol iteratively refine a design, then hand the agreed design to Claude Opus for implementation; or
- repeat a Fable-design/Sol-review loop ten times, ask Opus to implement the result, and invoke Sol to repair the implementation only when Fable rejects it.

Loops are Python `for` loops. Conditional escalation is an `if` statement. Parallel work uses `asyncio.gather`. There is no YAML workflow, graph builder, or special orchestration DSL.

Each agent works inside its own sandboxed Git worktree, so it cannot overwrite the original checkout or another agent's work. Agent turns produce Git-backed artifacts that can be reviewed, revised, neutrally verified, compared, selected, and applied as one auditable workflow.

## Install

Install the `h5i` engine:

```bash
curl -fsSL https://raw.githubusercontent.com/h5i-dev/h5i/main/install.sh | sh
```

Install the Python SDK from GitHub:

```bash
pip install "git+https://github.com/h5i-dev/h5i-python.git"
```

## Quickstart

Create `ensemble.py` inside the Git repository the agents should modify. This workflow let Claude and Codex independently implement the same task, review and improve each other’s work, and then select the better result.

```python
from h5i.orchestra import Conductor

async def main(task):
    async with Conductor(repo=".", run="demo-task", launcher="resident") as c:
        claude = await c.hire("claude-agent", runtime="claude")
        codex  = await c.hire("codex-agent",  runtime="codex")

        # Have both agents implement the task independently and in parallel
        claude_work, codex_work = await asyncio.gather(claude.work(task), codex.work(task))

        await c.freeze() # Seal the round, ensuring that neither agent influenced the other beforehand

        # Have each agent review the other's work
        await asyncio.gather(codex.review(claude_work), claude.review(codex_work))

        # Verify each submission in a fresh, neutral sandbox
        await c.verify(claude_work, ["pytest", "--quiet"])
        await c.verify(codex_work, ["pytest", "--quiet"])

        verdict = await c.judge() # Select the smallest diff among the submissions that pass all tests
        print("winner:", verdict.selected_submission)

asyncio.run(main("implement quicksort in python with unit test"))
```

Run it as a normal Python program:

```bash
python ensemble.py
```

With the default `launcher="resident"`, `h5i` automatically starts the agent sessions through `tmux`.

## Examples

See [examples/](./examples/) for complete scores, including:

- independent arena ranking;
- mutual-review ensembles;
- architect-to-implementer pipelines;
- debate-driven implementation;
- conditional review escalation;
- LLM judge panels;
- tournament brackets; and
- custom Python control flow.

## License

Apache-2.0
