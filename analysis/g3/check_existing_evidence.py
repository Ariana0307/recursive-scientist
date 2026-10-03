"""Offline G2 evidence checks only. Never imports torch/runner or launches a job."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import rfc8785

RUNNER = "4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8"
DATA = "6d958be074577803d12ecdefd02955f39262c83c16fe9348329d7fe0b5c001ce"
SPLIT = "48a8983fa5fdf95d137855c818b7bc716c476396dbe5b274eec41982b27e815e"
SOURCE_PATHS = ["runner/data.py", "runner/engine.py", "runner/cli.py", "runner/storage.py", "runner/supervisor.py", "runner/model.py", "schemas/contracts.py", "schemas/split.py"]

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_root", type=Path)
    parser.add_argument("source_checkout", type=Path)
    args = parser.parse_args()
    root, checkout = args.private_root, args.source_checkout
    rows = []
    for seed, expected_accuracy in [(42, 0.5646), (43, 0.5686)]:
        job = root / f"runs/RS-20261003-G2-r1-02-seed{seed}"
        attempt = job / "attempt-0001"
        request = json.loads((job / "request.json").read_bytes())
        result = json.loads((attempt / "result.json").read_bytes())
        execution = json.loads((attempt / "execution.json").read_bytes())
        provenance = json.loads((attempt / "provenance.json").read_bytes())
        data = json.loads((attempt / "data.json").read_bytes())
        indices = json.loads((attempt / "split-indices.json").read_bytes())
        assert result["status"] == "succeeded" and request["status"] == "approved"
        for key in ["schema_version", "experiment_id", "seed", "config", "config_hash", "code_version"]:
            assert request[key] == result[key], key
        assert request["seed"] == request["config"]["seed"] == seed
        assert request["code_version"] == provenance["code_commit"] == RUNNER
        assert not provenance["working_tree_dirty"] and provenance["mode"] == "full"
        assert hashlib.sha256(rfc8785.dumps(request["config"])).hexdigest() == request["config_hash"]
        assert hashlib.sha256(rfc8785.dumps(indices)).hexdigest() == SPLIT
        assert request["validation"]["split_indices_hash"] == result["validation"]["split_indices_hash"] == SPLIT
        train, validation = indices["train"], indices["validation"]
        assert len(train) == len(set(train)) == 45000 and len(validation) == len(set(validation)) == 5000
        assert set(train).isdisjoint(validation) and set(train) | set(validation) == set(range(50000))
        assert execution["train_count"] == 45000 and execution["validation_count"] == 5000
        assert execution["epochs"] == 1 and execution["diagnostic_only"] is False
        assert data["archive_sha256"] == DATA and data["official_test_read"] is False
        assert result["runtime"]["actual_device"] == "cuda" and result["runtime"]["elapsed_seconds"] <= 300
        assert result["validation"]["metrics"]["accuracy"] == expected_accuracy
        assert result["validation"]["metrics"]["loss"] >= 0
        files = [job / "request.json", *sorted(attempt.iterdir())]
        rows.append({"seed": seed, "metrics": result["validation"]["metrics"], "status": "PASSED_OFFLINE_REVALIDATION", "source_hashes": {str(f.relative_to(root)): digest(f) for f in files if f.is_file()}})
    ledger = root / "runs/.g1-quota"
    assert {f.name for f in ledger.iterdir()} == {"lock", "slot-1.json", "slot-2.json"}
    slots = [json.loads((ledger / f"slot-{n}.json").read_bytes()) for n in (1, 2)]
    assert [s["experiment_id"] for s in slots] == ["RS-20261003-G2-r1-02-seed42", "RS-20261003-G2-r1-02-seed43"]
    sources = {}
    for name in SOURCE_PATHS:
        actual = (checkout / name).read_bytes()
        pinned = subprocess.check_output(["git", "show", f"{RUNNER}:{name}"], cwd=checkout)
        assert actual == pinned, name
        sources[name] = {"sha256": hashlib.sha256(actual).hexdigest(), "matches_pinned_runner": True, "operator_can_write": os.access(checkout / name, os.W_OK)}
    print(json.dumps({"status": "PASSED_OFFLINE_REVALIDATION", "gpu_runs_this_check": 0, "campaign_status": "WAITING", "campaign_commit": "unknown", "runner_commit": RUNNER, "data_hash": DATA, "split_hash": SPLIT, "g2_results": rows, "quota_slots": slots, "source_audit": sources, "limitations": ["No new training, benchmark or test-set scoring", "Self-reported official_test_read is corroborated by source inspection, not a filesystem access trace", "Writable operator checkout does not prove a future Agent identity's permissions", "Two seeds cannot establish superiority, significance or a complete scientific loop"]}, indent=2))

if __name__ == "__main__":
    main()
