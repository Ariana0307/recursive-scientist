"""CPU-only G5 integration checks: no authorization API is called."""
import copy,hashlib,json
from pathlib import Path
import numpy as np
import pytest
from orchestrator.freeze_g5 import ROOT,freeze,canonical_hash,random_catalog
from orchestrator.validate_g5 import validate
from runner.search_plan import SearchPlan,bind_request,EVALUATION_HASH
from runner.search_authority import SearchAuthority
from runner.storage import AdmissionError

@pytest.fixture(autouse=True)
def forbid_authorize(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('SearchAuthority.authorize must not be called in G5')
    monkeypatch.setattr(SearchAuthority,'authorize',forbidden)

def plans():return [SearchPlan.model_validate_json((ROOT/f'runner/plans/search-worker-0{n}.json').read_bytes()) for n in (1,2)]

def test_frozen_inputs_and_evaluator():
    assert validate()['status']=='passed_draft_only'
    assert hashlib.sha256((ROOT/'runner/evaluate.py').read_bytes()).hexdigest()==EVALUATION_HASH

def test_single_global_permutation_and_round_projection():
    d=json.loads((ROOT/'configs/g5/random-global.json').read_text());p1,p2=plans()
    expected=np.random.Generator(np.random.PCG64(20261004)).permutation(18).tolist()[:6]
    assert [r['catalog_index'] for r in d['draws']]==expected and len(set(expected))==6
    assert random_catalog()[0]['augmentation']=='basic'
    for i,(a,b) in enumerate(zip(p1.trials,p2.trials)):
        assert a.seed==b.seed==42+i and a.arm!=b.arm
        random_trial=a if i%2==0 else b
        assert random_trial.arm=='random' and random_trial.random_parameters.model_dump()==d['draws'][i]['parameters']
        assert (b if i%2==0 else a).random_parameters is None

def test_two_roles_and_caps():
    pp=plans()
    assert [(p.role,p.max_starts) for p in pp]==[('01_train',6),('02_deploy',6)]
    for p in pp:
        assert [t.seed for t in p.trials]==list(range(42,48))
        assert sum(t.arm=='ai' for t in p.trials)==sum(t.arm=='random' for t in p.trials)==3
        assert p.status=='draft' and p.epochs==3 and p.batch_size==128 and p.timeout_seconds==300

def test_drafts_fail_before_authority_access(tmp_path):
    for p in plans():
        a=SearchAuthority(p,p.worker_id,p.role,tmp_path)
        with pytest.raises(AdmissionError,match='not approved'):a.load()
    assert list(tmp_path.iterdir())==[]

def test_round_seeds_from_trusted_plan_only():
    for p in plans():
        for n,t in enumerate(p.trials,1):
            params=(t.random_parameters.model_dump() if t.arm=='random' else {'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'})
            req=bind_request(p,n,json.dumps(params),'a'*40,p.worker_id,p.role)
            assert req.seed==41+n
            with pytest.raises(ValueError):bind_request(p,n,json.dumps(dict(params,seed=999)),'a'*40,p.worker_id,p.role)

def test_random_is_frozen_and_ai_first_source_is_preserved():
    p=plans()[0];params=p.trials[0].random_parameters.model_dump();params['augmentation']='none' if params['augmentation']=='basic' else 'basic'
    with pytest.raises(ValueError,match='precommitted'):bind_request(p,1,json.dumps(params),'a'*40,p.worker_id,p.role)
    initial=json.loads((ROOT/'configs/g5/ai-initial-proposal.json').read_text())
    assert initial['source_task']=='RS-20261003-G4' and initial['source_planner_record_sha256']
    assert initial['worker_id']=='worker-02' and initial['ai_trial']==1
