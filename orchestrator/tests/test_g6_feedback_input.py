"""Trusted ingestion boundaries with synthetic returned data only."""
import hashlib,json
import pytest
from orchestrator import feedback_input as f
from orchestrator.tests.test_ai_history import ai_pair
from runner import campaign
from schemas.contracts import ExperimentConfig,Result,Config,config_hash

@pytest.fixture
def returned(tmp_path,monkeypatch):
    monkeypatch.setattr(f,'RETURNED',tmp_path)
    monkeypatch.setattr(campaign,'current_commit',lambda:'c'*40)
    return tmp_path

def install(path,q,r):
    (path/'request.json').write_bytes(q);(path/'result.json').write_bytes(r)
    return hashlib.sha256(q).hexdigest(),hashlib.sha256(r).hexdigest()

@pytest.mark.parametrize('state',['succeeded','timed_out'])
def test_actual_contract_and_failed_outcome(returned,state):
    p,q,r=ai_pair('worker-02',1,state)
    data=f.ingest(*install(returned,q,r))
    assert data['current_round']==2 and len(data['records'])==4
    assert data['records'][-1]['status']==state
    assert all(x['origin'] in ('baseline','ai') for x in data['records'])

def test_missing_result_never_synthesized(returned):
    with pytest.raises(FileNotFoundError):f.ingest('a'*64,'b'*64)

def test_random_wrong_hash_wrong_first_config(returned):
    p,q,r=ai_pair('worker-01',1)
    with pytest.raises(ValueError,match='historical'):f.ingest(*install(returned,q,r))
    p,q,r=ai_pair('worker-02',1);install(returned,q,r)
    with pytest.raises(ValueError,match='hash'):f.ingest('0'*64,hashlib.sha256(r).hexdigest())
    obj=json.loads(q);obj['config']['learning_rate']=.001
    cfg=Config.model_validate_json(json.dumps(obj['config']));obj['config_hash']=config_hash(cfg)
    q=ExperimentConfig.model_validate_json(json.dumps(obj)).model_dump_json().encode()
    with pytest.raises(ValueError,match='historical'):f.ingest(*install(returned,q,r))
