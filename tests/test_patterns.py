"""The patterns are control flow — these tests script the server side and
assert the *shape* of what each pattern drives: turn ordering, freeze
placement, materials, early exits, citation validation, tie-breaks."""

import pytest

from h5i.orchestra import patterns
from mock_server import MockOrchestra, launch_conductor


def artifact_raw(owner: str, id_: str | None = None, **extra) -> dict:
    raw = {
        "id": id_ or f"sha:{owner}",
        "owner_agent": owner,
        "round": 1,
        "env_id": f"env/{owner}/x",
        "commit_oid": "c",
        "tree_oid": "t",
        "capture_ids": [],
        "files_changed": 1,
        "insertions": 1,
        "deletions": 0,
        "submitted_at": "2026-01-01T00:00:00Z",
        "independent": True,
    }
    raw.update(extra)
    return raw


def wire_basics(mock: MockOrchestra) -> None:
    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": f"env/{p['name']}/x"})
    mock.on("conductor.freeze", lambda p: {"id": "testrun", "phase": "sealed_submit"})
    mock.on("agent.work", lambda p: artifact_raw(p["agent"]))
    mock.on("conductor.verify", lambda p: {
        "id": f"verif:{p['artifact']['owner_agent']}",
        "submission_id": p["artifact"]["id"],
        "owner_agent": p["artifact"]["owner_agent"], "round": 1,
        "command": p["command"], "applies_cleanly": True, "tests_passed": True,
        "isolation": "workspace",
    })
    mock.on("conductor.judge", lambda p: {
        "selected_submission": "sha:claude", "method": p["policy"],
        "decided_by": "host", "can_auto_apply": True, "reasons": [],
    })


async def test_ensemble_reviews_revises_and_early_exits():
    mock = MockOrchestra()
    wire_basics(mock)
    cycle = {"n": 0}

    def review(p):
        reviewer, target = p["reviewer"], p["artifact"]["owner_agent"]
        # Cycle 1: codex demands changes from claude; everything else approves.
        body = (
            "needs work: missing tests"
            if cycle["n"] == 0 and reviewer == "codex" and target == "claude"
            else "APPROVE"
        )
        return {"reviewer": reviewer, "target": target, "round": 1, "body": body}

    def revise(p):
        cycle["n"] += 1  # claude's revision closes cycle 1
        return artifact_raw(p["agent"], id_=f"sha:{p['agent']}-r2")

    mock.on("agent.review", review)
    mock.on("agent.revise", revise)

    c = await launch_conductor(mock)
    try:
        claude = await c.hire("claude")
        codex = await c.hire("codex")
        outcome = await patterns.ensemble(
            c, "task", [claude, codex], rounds=3, verify=["true"]
        )
        # 2 attempts → freeze → cycle 1 (one revise) → cycle 2 all-approve → exit.
        assert outcome.rounds_run == 2
        assert len(outcome.reviews) == 4  # 2 ordered pairs × 2 cycles
        (revised,) = mock.calls_to("agent.revise")
        assert revised["agent"] == "claude"
        assert "[codex]" in revised["review"]["body"]  # merged-review format
        # Claude's artifact was replaced by the revision.
        by_owner = {a.owner_agent: a for a in outcome.artifacts}
        assert by_owner["claude"].id == "sha:claude-r2"
        # Both first attempts demanded independence.
        assert all(w["expect_independent"] for w in mock.calls_to("agent.work"))
        # Verify ran per artifact; the default policy judged.
        assert len(mock.calls_to("conductor.verify")) == 2
        assert outcome.verdict is not None
        # Freeze happened after the attempts and before any review.
        order = [m for m, _ in mock.calls if m.startswith(("agent.", "conductor.freeze"))]
        assert order.index("conductor.freeze") > max(
            i for i, m in enumerate(order) if m == "agent.work" and i < 4
        )
        assert order.index("conductor.freeze") < order.index("agent.review")
    finally:
        await c.close()


async def test_ensemble_requires_two_agents():
    mock = MockOrchestra()
    wire_basics(mock)
    c = await launch_conductor(mock)
    try:
        solo = await c.hire("solo")
        with pytest.raises(ValueError, match="two agents"):
            await patterns.ensemble(c, "task", [solo])
    finally:
        await c.close()


async def test_pipeline_freezes_after_first_and_feeds_materials():
    mock = MockOrchestra()
    wire_basics(mock)
    c = await launch_conductor(mock)
    try:
        architect = await c.hire("architect")
        builder = await c.hire("builder")
        artifacts = await patterns.pipeline(
            c, [(architect, "design"), (builder, "implement")]
        )
        assert [a.owner_agent for a in artifacts] == ["architect", "builder"]
        first, second = mock.calls_to("agent.work")
        assert "materials" not in first
        assert [m["owner_agent"] for m in second["materials"]] == ["architect"]
        methods = [m for m, _ in mock.calls]
        assert methods.index("conductor.freeze") == methods.index("agent.work") + 1
    finally:
        await c.close()


async def test_map_reduce_serializes_same_agent_and_reduces():
    mock = MockOrchestra()
    wire_basics(mock)
    counter = {"n": 0}

    def work(p):
        counter["n"] += 1
        return artifact_raw(p["agent"], id_=f"sha:{p['agent']}:{counter['n']}")

    mock.on("agent.work", work)
    c = await launch_conductor(mock)
    try:
        alice = await c.hire("alice")
        bob = await c.hire("bob")
        merger = await c.hire("merger")
        outcome = await patterns.map_reduce(
            c,
            [(alice, "part 1"), (bob, "part 2"), (alice, "part 3")],
            reduce=(merger, "merge the parts"),
        )
        assert len(outcome.parts) == 3
        assert outcome.merged is not None
        # Same-agent assignments ran sequentially, in order.
        alice_tasks = [w["task"] for w in mock.calls_to("agent.work") if w["agent"] == "alice"]
        assert alice_tasks == ["part 1", "part 3"]
        # The reducer got every part as material, after the freeze.
        merge_call = next(w for w in mock.calls_to("agent.work") if w["agent"] == "merger")
        assert len(merge_call["materials"]) == 3
    finally:
        await c.close()


async def test_arena_verifies_and_returns_rows():
    mock = MockOrchestra()
    wire_basics(mock)
    mock.on("conductor.compare", lambda p: [
        {"agent_id": "claude", "env_id": "e", "submitted": True, "status": "ok",
         "base_commit": "b", "files_changed": 1, "insertions": 1, "deletions": 0,
         "last_exit": 0, "last_counts": {}},
    ])
    c = await launch_conductor(mock)
    try:
        agents = [await c.hire("claude"), await c.hire("codex")]
        outcome = await patterns.arena(c, "task", agents, verify=["true"])
        assert len(outcome.artifacts) == 2
        assert outcome.verdict is not None
        assert outcome.rows[0].agent_id == "claude"
    finally:
        await c.close()


async def test_judge_panel_validates_citations_and_breaks_ties():
    mock = MockOrchestra()
    wire_basics(mock)
    # Two sealed candidates: same mean score, s2 has the smaller diff.
    s1 = artifact_raw("claude", id_="s1", files_changed=5, insertions=100)
    s2 = artifact_raw("codex", id_="s2", files_changed=1, insertions=2)
    verification = {
        "id": "v1", "submission_id": "s1", "owner_agent": "claude", "round": 1,
        "command": ["true"], "applies_cleanly": True, "tests_passed": True,
        "isolation": "workspace",
    }
    run_raw = {"id": "testrun", "phase": "sealed_submit",
               "submissions": [s1, s2], "verifications": [verification]}
    mock.on("conductor.status", lambda p: run_raw)

    asks = {"n": 0}

    def ask(p):
        asks["n"] += 1
        if asks["n"] == 1:  # first reply hallucinates a citation → re-asked
            return {"ballots": [
                {"artifact_id": "s1", "score": 7, "rationale": "…", "cited_ids": ["nope"]},
            ]}
        return {"ballots": [
            {"artifact_id": "s1", "score": 7, "rationale": "solid", "cited_ids": ["v1"]},
            {"artifact_id": "s2", "score": 7, "rationale": "lean", "cited_ids": ["s2"]},
        ]}

    mock.on("agent.ask", ask)
    mock.on("conductor.judge_begin", lambda p: {"replayed": False, "token": "judge#1", "run": run_raw})
    mock.on("conductor.judge_commit", lambda p: p["verdict"])

    c = await launch_conductor(mock)
    try:
        judge = await c.hire("judge")
        outcome = await patterns.judge_panel(c, "smallest correct change", [judge])
        assert asks["n"] == 2  # hallucinated citation was re-asked
        second_prompt = mock.calls_to("agent.ask")[1]["prompt"]
        assert "cited unknown evidence id 'nope'" in second_prompt
        # Tie on mean 7.0 → smallest diff wins.
        assert outcome.verdict.selected_submission == "s2"
        assert outcome.verdict.can_auto_apply is False
        assert "mean score 7.0/10" in outcome.verdict.reasons[0]
    finally:
        await c.close()


async def test_debate_alternates_and_concludes():
    mock = MockOrchestra()
    wire_basics(mock)

    def ask(p):
        prompt = p["prompt"]
        if "You moderate" in prompt:
            assert "- pro:" in prompt and "- con:" in prompt
            return {"winner": "pro", "rationale": "stronger case"}
        if "You open the debate" in prompt:
            return "opening argument"
        return "rebuttal"

    mock.on("agent.ask", ask)
    c = await launch_conductor(mock)
    try:
        pro = await c.hire("pro")
        con = await c.hire("con")
        moderator = await c.hire("mod")
        outcome = await patterns.debate(
            c, "tabs or spaces?", [pro, con], moderator=moderator, rounds=1
        )
        assert [who for who, _ in outcome.transcript] == ["pro", "con"]
        assert outcome.transcript[0][1] == "opening argument"
        assert outcome.conclusion is not None
        assert outcome.conclusion.winner == "pro"
    finally:
        await c.close()
