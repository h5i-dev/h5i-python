import asyncio

import pytest

from h5i.orchestra import (
    Artifact,
    AskParseError,
    ProtocolError,
    TurnContext,
    Verdict,
)
from mock_server import MockError, MockOrchestra, launch_conductor


def artifact_raw(owner: str, id_: str = "sha:1", **extra) -> dict:
    raw = {
        "id": id_,
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


async def test_launch_handshake_and_params():
    mock = MockOrchestra()
    c = await launch_conductor(
        mock,
        run="myrun",
        actor="human",
        turn_timeout=60,
        poll_interval=0.2,
        score_digest="abc123",
    )
    try:
        assert c.run_id == "testrun"  # what the server reports wins
        assert c.h5i_version == "0.0-mock"
        assert c.replayed_steps == 0
        (launch,) = mock.calls_to("conductor.launch")
        assert launch["run"] == "myrun"
        assert launch["actor"] == "human"
        assert launch["launcher"] == "attach"
        assert launch["turn_timeout_ms"] == 60000
        assert launch["poll_interval_ms"] == 200
        assert launch["score_digest"] == "abc123"
    finally:
        await c.close()


async def test_protocol_version_mismatch_refused():
    mock = MockOrchestra()
    mock.hello = dict(mock.hello, protocol_version=999)
    with pytest.raises(ProtocolError, match="protocol 999"):
        await launch_conductor(mock)


async def test_work_round_trip_preserves_unknown_fields():
    mock = MockOrchestra()
    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": f"env/{p['name']}/x"})
    mock.on("agent.work", lambda p: artifact_raw(p["agent"], future_field={"x": 1}))
    mock.on("conductor.verify", lambda p: {
        "id": "v1", "submission_id": p["artifact"]["id"], "owner_agent": "claude",
        "round": 1, "command": p["command"], "applies_cleanly": True,
        "tests_passed": True, "isolation": "workspace",
    })
    c = await launch_conductor(mock)
    try:
        claude = await c.hire("claude", runtime="claude", model="opus")
        (hire,) = mock.calls_to("agent.hire")
        assert hire == {"name": "claude", "runtime": "claude", "model": "opus"}

        await c.hire("codex", runtime="codex", model="gpt-5.4-mini", effort="medium")
        assert mock.calls_to("agent.hire")[-1]["effort"] == "medium"

        artifact = await claude.work("do it", expect_independent=True)
        (work,) = mock.calls_to("agent.work")
        assert work["expect_independent"] is True
        assert work["env_id"] == "env/claude/x"
        assert isinstance(artifact, Artifact) and artifact.independent

        verification = await c.verify(artifact, ["cargo", "test"])
        (verify,) = mock.calls_to("conductor.verify")
        # The unknown field made the round trip back to the server.
        assert verify["artifact"]["future_field"] == {"x": 1}
        assert verification.tests_passed

        with pytest.raises(TypeError, match="argv sequence"):
            await c.verify(artifact, "cargo test")
    finally:
        await c.close()


async def test_verify_sealed_from_passes_id_and_parses_seal_fields():
    mock = MockOrchestra()
    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": f"env/{p['name']}/x"})
    mock.on("agent.work", lambda p: artifact_raw(p["agent"], id_=f"sha:{p['agent']}"))
    mock.on("conductor.verify", lambda p: {
        "id": "v1", "submission_id": p["artifact"]["id"], "owner_agent": "coder",
        "round": 1, "command": p["command"], "applies_cleanly": True,
        "tests_passed": False, "isolation": "workspace",
        "sealed_from": p["sealed_from"], "sealed_tree_oid": "tree:tests",
        "sealed_paths": ["tests.sh"], "sealed_overridden": ["tests.sh"],
    })
    c = await launch_conductor(mock)
    try:
        coder = await c.hire("coder", runtime="claude")
        designer = await c.hire("designer", runtime="codex")
        candidate = await coder.work("implement")
        tests = await designer.work("design tests")

        # An Artifact seals by its submission id; a plain string passes through.
        v = await c.verify(candidate, ["sh", "tests.sh"], sealed_from=tests)
        assert mock.calls_to("conductor.verify")[-1]["sealed_from"] == tests.id
        await c.verify(candidate, ["sh", "tests.sh"], sealed_from="designer")
        assert mock.calls_to("conductor.verify")[-1]["sealed_from"] == "designer"

        # The seal evidence round-trips into the typed Verification.
        assert v.sealed
        assert v.sealed_from == tests.id
        assert v.sealed_tree_oid == "tree:tests"
        assert v.sealed_paths == ("tests.sh",)
        assert v.sealed_overridden == ("tests.sh",)

        # Unsealed requests omit the parameter entirely.
        mock.on("conductor.verify", lambda p: {
            "id": "v2", "submission_id": p["artifact"]["id"], "owner_agent": "coder",
            "round": 1, "command": p["command"], "applies_cleanly": True,
            "tests_passed": True, "isolation": "workspace",
        })
        plain = await c.verify(candidate, ["sh", "tests.sh"])
        assert "sealed_from" not in mock.calls_to("conductor.verify")[-1]
        assert not plain.sealed and plain.sealed_paths == ()
    finally:
        await c.close()


async def test_step_commit_replay_and_abort():
    mock = MockOrchestra()
    journal: dict[str, object] = {}
    seq: dict[str, int] = {}

    def begin(p):
        label = p["label"]
        seq[label] = seq.get(label, 0) + 1
        key = f"{label}#{seq[label]}"
        if key in journal:
            return {"replayed": True, "result": journal[key]}
        return {"replayed": False, "token": key}

    def commit(p):
        journal[p["token"]] = p["result"]
        return p["result"]

    mock.on("conductor.step_begin", begin)
    mock.on("conductor.step_commit", commit)
    mock.on("conductor.step_abort", lambda p: None)

    c = await launch_conductor(mock)
    try:
        calls = 0

        async def effect():
            nonlocal calls
            calls += 1
            return {"rows": 3}

        assert await c.step("fetch", effect) == {"rows": 3}
        assert calls == 1
        # Same key replayed: the closure must NOT run again.
        seq["fetch"] = 0
        assert await c.step("fetch", effect) == {"rows": 3}
        assert calls == 1

        # A raising closure aborts (releasing the label) and propagates.
        def bad():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await c.step("risky", bad)
        assert mock.calls_to("conductor.step_abort") == [{"token": "risky#1"}]

        # Scopes prefix labels.
        await c.scope("item/3").step("fetch", lambda: 1)
        assert any(
            p["label"] == "item/3/fetch" for p in mock.calls_to("conductor.step_begin")
        )
    finally:
        await c.close()


async def test_judge_builtin_and_custom_policy():
    mock = MockOrchestra()
    verdict_raw = {
        "selected_submission": "sha:1", "method": "tests_then_smallest_diff",
        "decided_by": "host", "can_auto_apply": True, "reasons": [],
    }
    run_raw = {"id": "testrun", "phase": "sealed_submit",
               "submissions": [artifact_raw("claude")]}
    mock.on("conductor.judge", lambda p: verdict_raw)
    mock.on("conductor.judge_begin", lambda p: {"replayed": False, "token": "judge#1", "run": run_raw})
    mock.on("conductor.judge_commit", lambda p: p["verdict"])
    mock.on("conductor.judge_abort", lambda p: None)

    c = await launch_conductor(mock)
    try:
        verdict = await c.judge()
        assert mock.calls_to("conductor.judge") == [{"policy": "tests_then_smallest_diff"}]
        assert verdict.selected_submission == "sha:1"

        # A custom policy sees the typed Run and its verdict is committed.
        def my_policy(run):
            assert run.id == "testrun"
            return Verdict(
                method="mine", decided_by="me",
                selected_submission=run.submissions[0].id,
            )

        verdict = await c.judge(my_policy)
        (commit,) = mock.calls_to("conductor.judge_commit")
        assert commit["verdict"]["method"] == "mine"
        assert verdict.method == "mine"

        # A raising policy aborts the judge step.
        def broken(_run):
            raise ValueError("cannot decide")

        with pytest.raises(ValueError, match="cannot decide"):
            await c.judge(broken)
        assert mock.calls_to("conductor.judge_abort") == [{"token": "judge#1"}]

        # Replayed verdicts skip the policy entirely.
        mock.on("conductor.judge_begin", lambda p: {"replayed": True, "verdict": verdict_raw})
        def never(run):
            raise AssertionError("policy ran on replay")

        replayed = await c.judge(never)
        assert replayed.method == "tests_then_smallest_diff"
    finally:
        await c.close()


async def test_ask_parse_retry_loop():
    mock = MockOrchestra()
    replies = iter(["not-a-number", 41, 42])
    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": "e"})
    mock.on("agent.ask", lambda p: next(replies))
    c = await launch_conductor(mock)
    try:
        agent = await c.hire("claude")

        def must_be_even_int(value):
            if not isinstance(value, int) or value % 2:
                raise ValueError(f"want an even int, got {value!r}")
            return value

        assert await agent.ask("give me an even int", parse=must_be_even_int) == 42
        asks = mock.calls_to("agent.ask")
        assert len(asks) == 3
        assert "could not be used" in asks[1]["prompt"]  # error context re-asked

        mock.on("agent.ask", lambda p: "never right")
        with pytest.raises(AskParseError):
            await agent.ask("hopeless", parse=must_be_even_int, attempts=2)
    finally:
        await c.close()


async def test_client_launcher_turn_dispatch():
    mock = MockOrchestra()
    turns: list[TurnContext] = []

    async def work(p):
        # The server delivers a turn mid-request and waits for the client.
        reply = await mock.request(
            "launcher.on_turn",
            {"run_id": "testrun", "agent_id": p["agent"], "env_id": p["env_id"],
             "kind": "work", "instruction": p["task"],
             "repo_workdir": "/r", "h5i_root": "/r/.h5i"},
        )
        assert reply.get("error") is None
        return artifact_raw(p["agent"])

    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": "e"})
    mock.on("agent.work", work)

    async def on_turn(turn: TurnContext):
        turns.append(turn)

    c = await launch_conductor(mock, on_turn=on_turn)
    try:
        (launch,) = mock.calls_to("conductor.launch")
        assert launch["launcher"] == "client"
        agent = await c.hire("claude")
        artifact = await agent.work("build the thing")
        assert artifact.owner_agent == "claude"
        assert len(turns) == 1
        assert turns[0].kind == "work"
        assert turns[0].instruction == "build the thing"
    finally:
        await c.close()


async def test_client_launcher_error_propagates_to_server():
    mock = MockOrchestra()

    async def work(p):
        reply = await mock.request("launcher.on_turn", {"kind": "work"})
        assert "no session" in reply["error"]["message"]
        raise MockError("launcher failed: no session")

    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": "e"})
    mock.on("agent.work", work)

    async def on_turn(_turn):
        raise RuntimeError("no session")

    c = await launch_conductor(mock, on_turn=on_turn)
    try:
        agent = await c.hire("claude")
        with pytest.raises(Exception, match="no session"):
            await agent.work("x")
    finally:
        await c.close()


async def test_hire_isolation_run_default_and_override():
    mock = MockOrchestra()
    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": "e"})
    c = await launch_conductor(mock, isolation="supervised")
    try:
        await c.hire("a", runtime="claude")            # inherits the run tier
        await c.hire("b", isolation="container")       # explicit override
        await c.hire("c", isolation="auto")            # back to auto-picking
        tiers = [p.get("isolation") for p in mock.calls_to("agent.hire")]
        assert tiers == ["supervised", "container", "auto"]
    finally:
        await c.close()

    # Without a run-level tier, hire sends nothing (server auto-picks).
    mock = MockOrchestra()
    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": "e"})
    c = await launch_conductor(mock)
    try:
        await c.hire("a")
        (hire,) = mock.calls_to("agent.hire")
        assert "isolation" not in hire
    finally:
        await c.close()


async def test_misc_surface_marshaling():
    mock = MockOrchestra()
    mock.on("conductor.freeze", lambda p: {"id": "testrun", "phase": "sealed_submit"})
    mock.on("conductor.status", lambda p: {"id": "testrun", "phase": "draft"})
    mock.on("conductor.note", lambda p: None)
    mock.on("conductor.patched", lambda p: True)
    mock.on("conductor.trace", lambda p: "orchestra trace — run 'testrun'")
    mock.on("gate.ask", lambda p: {"from": "human", "body": "APPROVE ship it"})
    mock.on("conductor.preflight", lambda p: None)
    mock.on("conductor.roster", lambda p: [{"agent_id": "a", "env_id": "e"}])

    c = await launch_conductor(mock)
    try:
        assert (await c.freeze()).phase == "sealed_submit"
        assert (await c.status()).phase == "draft"
        await c.note("hello")
        assert await c.patched("v2") is True
        assert "testrun" in await c.trace()
        answer = await c.gate("ship it?", to="reviewer")
        assert answer.approved and answer.sender == "human"
        assert mock.calls_to("gate.ask") == [{"question": "ship it?", "to": "reviewer"}]

        (roster_agent,) = await c.roster()
        await c.preflight(live=[roster_agent], min_isolation="workspace", clean_worktree=True)
        (preflight,) = mock.calls_to("conductor.preflight")
        assert preflight == {
            "live": [{"agent": "a", "env_id": "e"}],
            "min_isolation": "workspace",
            "clean_worktree": True,
        }
    finally:
        await c.close()


async def test_concurrent_agent_turns_gather():
    mock = MockOrchestra()
    started: list[str] = []
    release = asyncio.Event()

    async def work(p):
        started.append(p["agent"])
        await release.wait()
        return artifact_raw(p["agent"], id_=f"sha:{p['agent']}")

    mock.on("agent.hire", lambda p: {"agent_id": p["name"], "env_id": f"e/{p['name']}"})
    mock.on("agent.work", work)
    c = await launch_conductor(mock)
    try:
        claude = await c.hire("claude")
        codex = await c.hire("codex")
        gathered = asyncio.gather(claude.work("t"), codex.work("t"))
        while len(started) < 2:  # both turns in flight at once
            await asyncio.sleep(0.001)
        release.set()
        a, b = await gathered
        assert {a.owner_agent, b.owner_agent} == {"claude", "codex"}
    finally:
        await c.close()
