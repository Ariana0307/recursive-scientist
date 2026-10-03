"""Additional CPU-only G4 checks. All authority is synthetic in pytest tmp_path."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import pytest
from runner import campaign as budget, campaign_cli
from runner.storage import AdmissionError, atomic_new

EXPECTED_EVALUATOR = "68d34bb53116e8d1debc77b65b08320c52836a5b31414a7a32239b33b5d79bc7"

@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "PRIVATE", tmp_path)
    monkeypatch.setattr(budget, "current_commit", lambda: "a" * 40)
    return tmp_path

def params(seed=42):
    return json.dumps(dict(budget.policy()["fixed_config"], seed=seed))

def reserved():
    budget.authorize()
    req = budget.request_from_parameters(params())
    reservation = budget.reserve(req)
    attempt = budget.paths()[0] / "start-1"
    attempt.mkdir()
    atomic_new(attempt / "request.json", req.model_dump_json().encode())
    return req, reservation, attempt

def test_exact_requested_evaluator_digest():
    assert hashlib.sha256((budget.ROOT / "runner/evaluate.py").read_bytes()).hexdigest() == EXPECTED_EVALUATOR
    assert budget.policy()["evaluation_sha256"] == EXPECTED_EVALUATOR

def test_changed_evaluator_rejected_from_temporary_copy(isolated, monkeypatch):
    fake = isolated / "source"
    (fake / "runner").mkdir(parents=True)
    original = (budget.ROOT / "runner/evaluate.py").read_bytes()
    (fake / "runner/evaluate.py").write_bytes(original + b"\n# synthetic tamper\n")
    monkeypatch.setattr(budget, "ROOT", fake)
    with pytest.raises(AdmissionError, match="evaluator hash"):
        budget.policy()

def test_method_change_invalidates_existing_authority(isolated, monkeypatch):
    method = isolated / "method.json"
    method.write_bytes(budget.METHOD.read_bytes())
    monkeypatch.setattr(budget, "METHOD", method)
    budget.authorize()
    changed = json.loads(method.read_text())
    changed["statistics"]["sigma"] = "synthetic invalid replacement"
    method.write_text(json.dumps(changed))
    with pytest.raises(AdmissionError, match="committed policy"):
        budget.load_authority()

def test_child_rejects_different_parent_before_claim(isolated, monkeypatch):
    _, reservation, attempt = reserved()
    cap = budget.sealed_capability(reservation)
    monkeypatch.setattr(budget.os, "getppid", lambda: os.getpid() + 12345)
    try:
        with pytest.raises(AdmissionError, match="admitting parent"):
            budget.claim_child(cap)
        assert not (budget.paths()[1] / "claimed-1").exists()
    finally:
        os.close(cap)

def test_child_rejects_changed_request_before_claim(isolated, monkeypatch):
    _, reservation, attempt = reserved()
    replacement = budget.request_from_parameters(params(43))
    (attempt / "request.json").write_text(replacement.model_dump_json())
    cap = budget.sealed_capability(reservation)
    monkeypatch.setattr(budget.os, "getppid", lambda: os.getpid())
    try:
        with pytest.raises(AdmissionError, match="request mismatch"):
            budget.claim_child(cap)
        assert not (budget.paths()[1] / "claimed-1").exists()
    finally:
        os.close(cap)

def test_signed_reservation_blocks_replay_after_mirror_marker_removed(isolated, monkeypatch):
    _, reservation, attempt = reserved()
    cap = budget.sealed_capability(reservation)
    monkeypatch.setattr(budget.os, "getppid", lambda: os.getpid())
    try:
        budget.claim_child(cap)
        (attempt / "child-started").unlink()
        with pytest.raises(FileExistsError):
            budget.claim_child(cap)
        assert (budget.paths()[1] / "claimed-1").exists()
    finally:
        os.close(cap)

def test_actual_child_entry_checks_before_training_stub(isolated, monkeypatch):
    _, reservation, _ = reserved()
    cap = budget.sealed_capability(reservation)
    calls = []
    monkeypatch.setattr(budget.os, "getppid", lambda: os.getpid())
    monkeypatch.setenv("RS_G3_CAP_FD", str(cap))
    monkeypatch.setattr(sys, "argv", ["campaign_cli", "_child"])
    monkeypatch.setattr(campaign_cli, "check_checkout", lambda req: calls.append("checkout"))
    def env():
        calls.append("environment")
        return {}
    monkeypatch.setattr(campaign_cli, "check_environment", env)
    monkeypatch.setattr(campaign_cli, "train_job", lambda *args: calls.append("training_stub_only"))
    try:
        assert campaign_cli.main() == 0
        assert calls == ["checkout", "environment", "training_stub_only"]
    finally:
        os.close(cap)
