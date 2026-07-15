"""Agentless: Demystifying LLM-based Software Engineering Agents (Xia et
al. 2024, arXiv:2407.01489) — three fixed phases, no agentic wandering.

Agentless argues that for repository work a *fixed* pipeline beats an
autonomous agent deciding its own next action: hierarchical localization
(repository structure → files → specific elements), minimal repair, then
validation. Here the file tree and file excerpts are journaled ``step``
effects (a resume replays the exact same view of the repo), localization
is two validated-JSON ``ask`` turns, repair is one work turn constrained
to the located files, and validation is neutral verification.

    python examples/papers/agentless.py ["<issue>"]
    # default issue: implement quicksort with pytest
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

from h5i.orchestra import Conductor

DEMO_ISSUE = "implement quicksort with pytest"
VERIFY = ["pytest", "-q"]
MAX_FILES = 3
TREE_LIMIT = 200  # files listed to the locator
EXCERPT_CHARS = 2_000  # per-file excerpt shown for element localization

SKIP_PARTS = {".git", ".venv", "node_modules", "__pycache__", "target"}


def repo_tree() -> list[str]:
    files = [
        str(p)
        for p in sorted(Path(".").rglob("*"))
        if p.is_file() and not (set(p.parts) & SKIP_PARTS)
    ]
    return files[:TREE_LIMIT]


def excerpts(paths: list[str]) -> str:
    parts = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            text = f"(unreadable: {e})"
        parts.append(f"--- {path} ---\n{text[:EXCERPT_CHARS]}")
    return "\n\n".join(parts)


def parse_files(known: list[str]):
    def parse(value: Any) -> list[str]:
        files = value.get("files") if isinstance(value, dict) else value
        if not isinstance(files, list) or not files:
            raise ValueError('reply must be {"files": ["<path from the tree>", ...]}')
        chosen = [str(f).strip() for f in files][:MAX_FILES]
        unknown = [f for f in chosen if f not in known]
        if unknown:
            raise ValueError(f"paths not in the repository tree: {unknown}")
        return chosen

    return parse


def parse_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


async def main(issue: str) -> None:
    async with Conductor(".", "agentless-demo", launcher="resident", isolation="supervised") as c:
        locator = await c.hire("locator", runtime="claude", model="claude-haiku-4-5")
        fixer = await c.hire("fixer", runtime="claude", model="claude-haiku-4-5")

        # Phase 1a — file-level localization over the journaled repo tree.
        tree = await c.step("repo-tree", repo_tree)
        files = await locator.ask(
            f"Issue: {issue}\n\nRepository files:\n" + "\n".join(tree) + "\n\n"
            f"Which files (at most {MAX_FILES}) must change to resolve the "
            "issue? If the change belongs in a NEW file, pick the closest "
            'existing neighbors instead. Reply as JSON: {"files": ["..."]}',
            parse=parse_files(tree),
        )
        print("located files:", ", ".join(files))

        # Phase 1b — element-level localization inside the located files.
        content = await c.scope("excerpts").step("read", lambda: excerpts(files))
        elements = await locator.ask(
            f"Issue: {issue}\n\nLocated file excerpts:\n{content}\n\n"
            "Name the specific elements (functions, classes, sections — or "
            "new ones to add, and where) that the fix should touch, with one "
            "line of rationale each. Reply as a single JSON string.",
            parse=parse_text,
        )
        print(f"located elements:\n{elements}")

        # Phase 2 — repair: a minimal patch confined to the located scope.
        artifact = await fixer.work(
            f"Resolve this issue with a MINIMAL change: {issue}\n\n"
            f"Confine your edit to these locations:\nfiles: {', '.join(files)}\n"
            f"elements:\n{elements}\n\nDo not refactor beyond the fix.",
            expect_independent=True,
        )
        await c.freeze()

        # Phase 3 — validation.
        await c.verify(artifact, VERIFY)
        verdict = await c.judge()
        print("verdict:", verdict.selected_submission or "none", "—", *verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEMO_ISSUE))
