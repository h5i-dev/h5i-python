"""Define-by-run means ordinary Python is the workflow language.

This score shows the pieces no manifest could express: data turns feeding
`if`, a journaled fan-out over a dynamic work list, a custom (LLM-assisted)
verdict policy, and a mid-run score migration marker.
"""

import asyncio

from h5i.orchestra import Conductor, Verdict, patterns


async def main() -> None:
    async with Conductor(".", "triage-and-fix") as c:
        lead = await c.hire("lead", runtime="claude")
        crew = [await c.hire(f"fixer{i}", runtime="claude") for i in range(2)]

        # A data turn: the agent replies with JSON, not code. The reply is
        # journaled — on resume this list comes back without re-asking.
        hotspots: list = await lead.ask(
            "List up to 4 modules with failing or flaky tests as a JSON "
            'array: [{"path": "...", "symptom": "..."}]',
            parse=lambda v: list(v),
        )
        if not hotspots:
            print("nothing to fix")
            return

        # Journal any host-side effect exactly-once; distinct labels for
        # parallel loops come from scopes.
        for i, spot in enumerate(hotspots):
            await c.scope(f"triage/{i}").step(
                "log", lambda spot=spot: f"queued {spot['path']}"
            )

        # Dynamic fan-out: assignments follow the data, round-robin.
        outcome = await patterns.map_reduce(
            c,
            [
                (crew[i % len(crew)], f"fix `{s['path']}`: {s['symptom']}")
                for i, s in enumerate(hotspots)
            ],
            reduce=(lead, "merge every fix into one coherent candidate"),
        )
        merged = outcome.merged
        assert merged is not None

        # A migration marker: flip behavior for new runs while an in-flight
        # journal keeps replaying the path it recorded.
        if await c.patched("verify-in-container"):
            await c.verify(merged, ["pytest", "-q"], isolation="container")
        else:
            await c.verify(merged, ["pytest", "-q"])

        # A custom policy is just a function over the folded run.
        def only_if_green(run) -> Verdict:
            latest = {v.submission_id: v for v in run.verifications}
            good = latest.get(merged.id)
            if good and good.tests_passed and good.applies_cleanly:
                return Verdict(
                    method="custom:only-if-green",
                    decided_by="triage-and-fix score",
                    selected_submission=merged.id,
                    can_auto_apply=True,
                    reasons=("merged candidate is green",),
                )
            return Verdict(
                method="custom:only-if-green",
                decided_by="triage-and-fix score",
                reasons=("merged candidate failed neutral verification",),
            )

        verdict = await c.judge(only_if_green)
        print("verdict:", verdict.reasons)


if __name__ == "__main__":
    asyncio.run(main())
