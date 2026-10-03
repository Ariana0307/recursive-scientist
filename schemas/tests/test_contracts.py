"""Synthetic contract fixtures only: these are NOT experiment measurements."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
import rfc8785
from pydantic import ValidationError
from schemas.contracts import Config, ExperimentConfig, Result, Decision, config_hash, match_result, retry_action
from schemas.split import split_indices, split_hash

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def payload():
    return json.loads((ROOT / "configs/baseline.json").read_text())

def valid(payload):
    return ExperimentConfig.model_validate_json(json.dumps(payload))

def test_baseline_and_canonical_hash(payload):
    request = valid(payload)
    assert request.config_hash == hashlib.sha256(rfc8785.dumps(payload["config"])).hexdigest()
    assert config_hash(Config.model_validate(dict(reversed(list(payload["config"].items()))))) == request.config_hash
    assert valid(json.loads(request.model_dump_json())) == request

@pytest.mark.parametrize("parent,key", [(None,"command"),("config","input_path"),("config","code"),("runtime","shell"),("validation","test")])
def test_unknown_fields(payload,parent,key):
    target = payload if parent is None else payload[parent]
    target[key] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs"):
        valid(payload)

@pytest.mark.parametrize("key,value", [
    ("learning_rate",0),("learning_rate",0.11),("learning_rate",float("nan")),
    ("weight_decay",float("inf")),("weight_decay",-0.1),("weight_decay",0.02),
    ("epochs",0),("epochs",4),("epochs",True),("batch_size",17),("batch_size",16.0),
    ("seed",-1),("seed",2**32),("seed",True),("seed","42"),
    ("split_seed",1),("split_seed",20261003.0),("timeout_seconds",301),
    ("augmentation","exec"),("model","arbitrary"),("dataset","test")])
def test_bad_config(payload,key,value):
    payload["config"][key] = value
    with pytest.raises(ValidationError): valid(payload)

def test_seed_mismatch(payload):
    payload["seed"] += 1
    with pytest.raises(ValidationError,match="seed differs"): valid(payload)

def test_hash_mismatch(payload):
    payload["config_hash"] = "0"*64
    with pytest.raises(ValidationError,match="config_hash"): valid(payload)

def test_runtime_mismatch(payload):
    payload["runtime"]["timeout_seconds"] = 299
    with pytest.raises(ValidationError,match="timeout differs"): valid(payload)

def test_no_traversal(payload):
    payload["experiment_id"] = "../oops"
    with pytest.raises(ValidationError): valid(payload)

def test_split_golden():
    train, val = split_indices()
    assert len(train)==45000 and len(val)==5000
    assert set(train).isdisjoint(val)
    assert set(train)|set(val)==set(range(50000))
    manifest=json.loads((ROOT/"schemas/split_manifest.json").read_text())
    assert split_hash()==manifest["split_indices_hash"]

def test_split_hash_rejected(payload):
    payload["validation"]["split_indices_hash"]="0"*64
    with pytest.raises(ValidationError,match="split_indices_hash"): valid(payload)

def result_fixture(payload):
    data=copy.deepcopy(payload)
    data.update(status="succeeded",error=None,
        validation={"split_id":payload["validation"]["split_id"],"split_indices_hash":split_hash(),"metrics":{"accuracy":0.5,"loss":1.0}},
        runtime={"elapsed_seconds":1.0,"started_at":"2026-10-03T00:00:00Z","finished_at":"2026-10-03T00:00:01Z","actual_device":"cuda"})
    return data

def test_result_binding(payload):
    result=Result.model_validate_json(json.dumps(result_fixture(payload)))
    match_result(valid(payload),result)
    changed=copy.deepcopy(payload); changed["code_version"]="a"*40
    with pytest.raises(ValueError,match="code_version"): match_result(valid(changed),result)

@pytest.mark.parametrize("accuracy",[1.1,-0.1,float("nan"),float("inf")])
def test_invalid_metrics(payload,accuracy):
    result=result_fixture(payload); result["validation"]["metrics"]["accuracy"]=accuracy
    with pytest.raises(ValidationError): Result.model_validate_json(json.dumps(result))

@pytest.mark.parametrize("status,kind",[("failed","execution"),("timed_out","timeout"),("cancelled","cancelled")])
def test_failures_need_null_metrics(payload,status,kind):
    result=result_fixture(payload); result.update(status=status,error={"kind":kind,"message":"synthetic contract test"})
    with pytest.raises(ValidationError): Result.model_validate_json(json.dumps(result))
    result["validation"]["metrics"]={"accuracy":None,"loss":None}
    Result.model_validate_json(json.dumps(result))

def test_bad_timestamp_and_timeout(payload):
    result=result_fixture(payload); result["runtime"]["started_at"]="2026-10-03T00:00:00"
    with pytest.raises(ValidationError): Result.model_validate_json(json.dumps(result))
    result=result_fixture(payload); result["runtime"]["elapsed_seconds"]=301.0
    with pytest.raises(ValidationError): Result.model_validate_json(json.dumps(result))

def test_retry_and_conflicts(payload):
    req=valid(payload)
    assert retry_action(req,req,"running")=="in_progress"
    assert retry_action(req,req,"succeeded")=="reuse"
    assert retry_action(req,req,"timed_out")=="retry"
    other=copy.deepcopy(payload); other["config"]["learning_rate"]=0.002
    other["config_hash"]=config_hash(Config.model_validate(other["config"]))
    with pytest.raises(ValueError,match="conflict"): retry_action(req,valid(other),"failed")
    other=copy.deepcopy(payload); other["code_version"]="b"*40
    with pytest.raises(ValueError,match="conflict"): retry_action(req,valid(other),"failed")

def test_decision_semantics(payload):
    data=copy.deepcopy(payload)
    data.update(status="propose_next",validation={"split_id":payload["validation"]["split_id"],"split_indices_hash":split_hash(),"metrics":{"accuracy":None,"loss":None},"objective":"maximize"},
        runtime={"elapsed_seconds":0.1},rationale="Synthetic retry proposal after failure",evidence_result_id=payload["experiment_id"],next_experiment_id="next-test-id",strategy_version="v1")
    Decision.model_validate_json(json.dumps(data))
    data["next_experiment_id"]=data["experiment_id"]
    with pytest.raises(ValidationError): Decision.model_validate_json(json.dumps(data))
