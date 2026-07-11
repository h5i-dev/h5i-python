from h5i.orchestra import Artifact, GateAnswer, Review, Verdict
from h5i.orchestra._types import approves_text


class TestApprovalConvention:
    """Port-fidelity tests for the Rust `first_token_approves` heuristic."""

    def test_plain_tokens(self):
        assert approves_text("APPROVE")
        assert approves_text("approved, nice work")
        assert approves_text("LGTM!")
        assert approves_text("yes")
        assert approves_text("OK to merge")

    def test_labeled_verdicts(self):
        assert approves_text("Verdict: approve")
        assert approves_text("Decision: LGTM")
        assert approves_text("Result:  APPROVED — clean diff")
        assert approves_text("status: ok")

    def test_leading_line_selection(self):
        assert approves_text("\n\n  APPROVE\nbut see nits below")
        assert not approves_text("")
        assert not approves_text("\n \n")

    def test_conservative_negatives(self):
        assert not approves_text("I can't approve this")
        assert not approves_text("changes before approve")
        assert not approves_text("Needs work. APPROVE later.")
        assert not approves_text("Summary: approve")  # unknown label ≠ approval label

    def test_edge_trimming_matches_rust(self):
        assert approves_text("**APPROVE**")  # edges trimmed
        assert not approves_text("AP-PROVE")  # interior punctuation kept


class TestRawRoundTrip:
    def test_artifact_preserves_unknown_fields(self):
        raw = {
            "id": "sha:1",
            "owner_agent": "claude",
            "round": 1,
            "env_id": "env/claude/x",
            "commit_oid": "c",
            "tree_oid": "t",
            "capture_ids": [],
            "files_changed": 2,
            "insertions": 10,
            "deletions": 3,
            "submitted_at": "2026-01-01T00:00:00Z",
            "independent": True,
            "a_field_from_the_future": {"x": 1},
        }
        artifact = Artifact.from_raw(raw)
        assert artifact.id == "sha:1"
        assert artifact.independent is True
        assert artifact.summary is None
        # The full payload — unknown fields included — goes back over the wire.
        assert artifact.to_payload()["a_field_from_the_future"] == {"x": 1}

    def test_constructed_verdict_payload(self):
        verdict = Verdict(
            method="mine", decided_by="me", selected_submission="sha:1", reasons=("r",)
        )
        assert verdict.to_payload() == {
            "method": "mine",
            "decided_by": "me",
            "selected_submission": "sha:1",
            "can_auto_apply": False,
            "reasons": ["r"],
        }

    def test_review_approved_and_payload(self):
        review = Review.from_raw(
            {"reviewer": "codex", "target": "claude", "round": 1, "body": "Verdict: approve"}
        )
        assert review.approved
        merged = Review(reviewer="a+b", target="c", round=1, body="no")
        assert merged.to_payload()["reviewer"] == "a+b"
        assert not merged.approved

    def test_gate_answer(self):
        answer = GateAnswer.from_raw({"from": "human", "body": "APPROVE go ahead"})
        assert answer.sender == "human"
        assert answer.approved
