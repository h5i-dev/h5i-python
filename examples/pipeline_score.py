"""Pipeline: role-specialized stages in sequence — architect designs,
implementer builds, hardener tests. Each later stage receives the previous
stage's artifact as granted material (honestly stamped non-independent, with
influence edges in the event log).

Stage 1 works pre-freeze; the round seals right after it, because materials
ride the sealed-phase-only discuss channel.

    python examples/pipeline_score.py
"""

import asyncio

from h5i.orchestra import Conductor, patterns

FEATURE = "add `--json` output to `h5i vibe`"


async def main() -> None:
    async with Conductor(".", "pipeline-demo", launcher="resident") as c:
        architect = await c.hire("architect", runtime="claude")
        builder = await c.hire("builder", runtime="codex")
        hardener = await c.hire("hardener", runtime="claude")

        design, impl, hardened = await patterns.pipeline(
            c,
            [
                (
                    architect,
                    f"Design {FEATURE}: write docs/design-vibe-json.md with the "
                    "schema, flag semantics, and test plan. Submit only the doc.",
                ),
                (
                    builder,
                    "Implement the granted design exactly. If the design is "
                    "ambiguous, choose the smallest reading and note it in "
                    "your summary.",
                ),
                (
                    hardener,
                    "The granted artifact implements the feature. Add edge-case "
                    "tests (empty repo, no commits, huge history) and fix what "
                    "they catch. Keep the diff additive where possible.",
                ),
            ],
        )
        print("stages:", [(a.owner_agent, a.id) for a in (design, impl, hardened)])

        # The final artifact carries the whole chain; verify and gate that one.
        verification = await c.verify(hardened, ["cargo", "test", "--quiet"])
        print("tests passed:", verification.tests_passed)
        if verification.tests_passed and (await c.gate("apply the pipeline result?")).approved:
            await c.apply(hardened, force=True)  # force: our gate is the verdict


if __name__ == "__main__":
    asyncio.run(main())
