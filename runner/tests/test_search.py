"""Synthetic CPU fixtures only. Never create real campaign authorization or train."""
import copy,hashlib,json,os,multiprocessing,random
from pathlib import Path
import pytest
from runner import search_authority as auth
from runner.search_plan import SearchPlan,EVALUATION_HASH,Parameters,bind_request
from runner.storage import AdmissionError,atomic_new
from runner.cli import result_payload
from runner import model_artifact as artifact

ROOT=Path(__file__).resolve().parents[2]


def example():return json.loads((ROOT/'runner/plans/search-worker-01.json').read_text())


@pytest.fixture
def authority(tmp_path,monkeypatch):
    obj=example();obj['status']='approved_for_future_execution'
    p=tmp_path/'versioned-plan.json';p.write_text(json.dumps(obj))
    monkeypatch.setattr(auth,'PLAN_FILES',{'worker-01':p})
    monkeypatch.setattr(auth.legacy,'current_commit',lambda:'a'*40)
    a=auth.SearchAuthority(SearchPlan.model_validate_json(json.dumps(obj)),'worker-01','01_train',tmp_path/'private')
    a.authorize()
    return a


def raw(a,n):
    trial=a.plan.trials[n-1]
    return (trial.random_parameters or Parameters(learning_rate=.001,weight_decay=.0001,augmentation='none')).model_dump_json()


def reserve_closed(a,n,status='failed'):
    req,slot=a.reserve(raw(a,n));path=a.campaign/f'start-{n}';path.mkdir()
    atomic_new(path/'request.json',req.model_dump_json().encode())
    result=result_payload(req,status,'2026-10-03T00:00:00Z',1.,'cuda',None,{'kind':'execution','message':'synthetic only'})
    atomic_new(path/'result.json',result.model_dump_json().encode())
    return req,slot,path


def test_draft_never_authorizes(tmp_path):
    a=auth.SearchAuthority(SearchPlan.model_validate_json(json.dumps(example())),'worker-01','01_train',tmp_path)
    with pytest.raises(AdmissionError,match='draft'):a.authorize()
    with pytest.raises(AdmissionError,match='not approved'):a.load()
    assert not (tmp_path/'search-authority').exists()


@pytest.mark.parametrize('field,value',[('max_starts',7),('max_starts',True),('epochs',2),('batch_size',64),('timeout_seconds',301),('split_seed',1),('campaign_id','../oops'),('extra','shell')])
def test_plan_out_of_bounds(field,value):
    obj=example();obj[field]=value
    with pytest.raises(ValueError):SearchPlan.model_validate_json(json.dumps(obj))


def test_plan_roles_seeds_and_arms():
    obj=example();obj['trials'][0]['seed']=True
    with pytest.raises(ValueError):SearchPlan.model_validate_json(json.dumps(obj))
    obj=example();obj['trials'][1]={'arm':'random','seed':42,'random_parameters':obj['trials'][0]['random_parameters']}
    with pytest.raises(ValueError):SearchPlan.model_validate_json(json.dumps(obj))
    p=SearchPlan.model_validate_json(json.dumps(example()))
    with pytest.raises(ValueError,match='role'):bind_request(p,1,json.dumps(example()['trials'][0]['random_parameters']),'a'*40,'worker-01','wrong')
    with pytest.raises(AdmissionError,match='role'):auth.SearchAuthority(p,'worker-02','01_train')


@pytest.mark.parametrize('field,value',[('seed',44),('role','02_train'),('campaign','evil'),('path','evil'),('command','sh'),('max_starts',10),('learning_rate',.1),('weight_decay',True)])
def test_model_cannot_override_plan(authority,field,value):
    obj=json.loads(raw(authority,1));obj[field]=value
    with pytest.raises(ValueError):authority.reserve(json.dumps(obj))
    assert authority.slots()==[]


def test_tamper_auth_and_full_child_request(authority,monkeypatch):
    p=authority.campaign/'authorization.json';p.chmod(0o600);original=p.read_bytes();obj=json.loads(original);obj['payload']['plan']['max_starts']=99;p.write_text(json.dumps(obj))
    with pytest.raises(AdmissionError):authority.load()
    p.write_bytes(original);p.chmod(0o400)
    req,slot=authority.reserve(raw(authority,1));run=authority.campaign/'start-1';run.mkdir()
    obj=json.loads(req.model_dump_json());obj['seed']=43;obj['config']['seed']=43
    from schemas.contracts import Config,config_hash
    obj['config_hash']=config_hash(Config.model_validate(obj['config']))
    atomic_new(run/'request.json',json.dumps(obj).encode())
    fd=authority.capability(slot);monkeypatch.setattr(auth.os,'getppid',lambda:os.getpid())
    try:
        with pytest.raises(AdmissionError,match='seed'):authority.claim(fd)
        assert not (authority.authority/'claimed-1').exists()
    finally:os.close(fd)


def test_child_one_use_and_missing_signature(authority,monkeypatch):
    req,slot=authority.reserve(raw(authority,1));run=authority.campaign/'start-1';run.mkdir();atomic_new(run/'request.json',req.model_dump_json().encode())
    fd=authority.capability(slot);monkeypatch.setattr(auth.os,'getppid',lambda:os.getpid())
    try:
        assert authority.claim(fd)[0]==req
        with pytest.raises(FileExistsError):authority.claim(fd)
    finally:os.close(fd)


def test_parallel_last_slot_failure_count_and_two_arm_cap(authority):
    for n in range(1,6):reserve_closed(authority,n)
    import subprocess,sys
    script="""import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from runner import search_authority as auth
from runner.search_plan import SearchPlan
from runner.storage import AdmissionError
auth.legacy.current_commit=lambda:'a'*40
plan=SearchPlan.model_validate_json(Path(sys.argv[2]).read_bytes())
a=auth.SearchAuthority(plan,'worker-01','01_train',Path(sys.argv[3]))
try:a.reserve(sys.argv[4]);raise SystemExit(0)
except AdmissionError:raise SystemExit(3)
"""
    args=[sys.executable,'-I','-B','-c',script,str(ROOT),str(auth.PLAN_FILES['worker-01']),str(authority.private),raw(authority,6)]
    workers=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(6)]
    codes=[]
    for proc in workers:
        out,err=proc.communicate(timeout=15);assert proc.returncode in (0,3),err.decode();codes.append(proc.returncode)
    assert codes.count(0)==1 and codes.count(3)==5
    assert len(authority.slots())==6
    assert sum(s['arm']=='random' for s in authority.slots())==3
    assert sum(s['arm']=='ai' for s in authority.slots())==3
    with pytest.raises(AdmissionError,match='exhausted'):authority.reserve(raw(authority,6))


def test_wrong_random_parameters(authority):
    obj=json.loads(raw(authority,1));obj['augmentation']='none' if obj['augmentation']=='basic' else 'basic'
    with pytest.raises(ValueError,match='precommitted'):authority.reserve(json.dumps(obj))
    assert authority.slots()==[]


def test_artifact_roundtrip_rng_and_failure_gating(tmp_path):
    import numpy as np
    import torch
    from runner.model import small_cnn
    p=SearchPlan.model_validate_json(json.dumps(example()))
    req=bind_request(p,2,json.dumps({'learning_rate':.001,'weight_decay':.0001,'augmentation':'none'}),'a'*40,'worker-01','01_train')
    torch.set_num_threads(2);torch.manual_seed(42);np.random.seed(42);random.seed(42)
    model=small_cnn();other=small_cnn();x=torch.zeros(2,3,32,32)
    before=model(x).detach().clone();rng=torch.random.get_rng_state().clone();nrng=np.random.get_state();prng=random.getstate()
    gen=torch.Generator().manual_seed(77);grng=gen.get_state().clone()
    metadata=artifact.stage(model,tmp_path,req,EVALUATION_HASH)
    artifact.publish_pending(tmp_path,req,EVALUATION_HASH)
    with pytest.raises(FileNotFoundError):artifact.load_success(tmp_path,req,EVALUATION_HASH)
    result=result_payload(req,'succeeded','2026-10-03T00:00:00Z',1.,'cuda',{'accuracy':.5,'loss':1.0},None)
    atomic_new(tmp_path/'result.json',result.model_dump_json().encode())
    state,loaded=artifact.load_success(tmp_path,req,EVALUATION_HASH);other.load_state_dict(state)
    assert torch.equal(before,other(x))
    assert torch.equal(rng,torch.random.get_rng_state()) and torch.equal(grng,gen.get_state())
    assert np.array_equal(nrng[1],np.random.get_state()[1]) and nrng[2:]==np.random.get_state()[2:]
    assert prng==random.getstate() and loaded==metadata
    assert not torch.cuda.is_initialized()
    # A failed/cancelled terminal marker denies even physically present weights.
    result=result_payload(req,'cancelled','2026-10-03T00:00:00Z',1.,'cuda',None,{'kind':'cancelled','message':'synthetic'})
    (tmp_path/'result.json').write_text(result.model_dump_json())
    with pytest.raises(AdmissionError,match='failed/cancelled'):artifact.load_success(tmp_path,req,EVALUATION_HASH)


def test_evaluator_unchanged_and_g3_source_unchanged():
    import subprocess
    assert hashlib.sha256((ROOT/'runner/evaluate.py').read_bytes()).hexdigest()==EVALUATION_HASH
    for file in ['campaign.py','campaign_cli.py','campaign_summary.py','g3-method.json']:
        original=subprocess.check_output(['git','show','931049af15ddafa12a5163e924a3ea84bbfbbf3f:runner/'+file],cwd=ROOT)
        assert original==(ROOT/'runner'/file).read_bytes()


def test_search_engine_only_appends_post_score_artifact_logic():
    import subprocess
    current=(ROOT/'runner/engine.py').read_text()
    insertion="        if context.get('save_state_dict'):\n            from runner.model_artifact import stage\n            stage(model, attempt, request, context['evaluation_sha256'])\n"
    original=subprocess.check_output(['git','show','931049af15ddafa12a5163e924a3ea84bbfbbf3f:runner/engine.py'],cwd=ROOT,text=True)
    assert current.count(insertion)==1 and current.replace(insertion,'')==original


def test_search_parent_publishes_only_matching_success(authority,monkeypatch):
    import torch
    from runner import search_cli
    from runner.storage import json_new
    from runner.model import small_cnn
    monkeypatch.setattr(search_cli,'check_environment',lambda:{})
    monkeypatch.setattr(search_cli,'check_checkout',lambda req:None)
    def synthetic(command,timeout,log,env,pass_fds):
        slot=authority.slots()[-1];n=slot['slot'];path=authority.campaign/f'start-{n}'
        from schemas.contracts import ExperimentConfig
        req=ExperimentConfig.model_validate_json((path/'request.json').read_bytes())
        json_new(path/'device.json',{'actual_device':'cuda'})
        artifact.stage(small_cnn(),path,req,EVALUATION_HASH)
        json_new(path/'outcome.json',{'status':'succeeded','metrics':{'accuracy':.5,'loss':1.0},'error':None})
        return 'finished',1.0,0
    monkeypatch.setattr(search_cli,'supervise',synthetic)
    result=search_cli.run(raw(authority,1),authority)
    assert result['status']=='succeeded'
    from schemas.contracts import ExperimentConfig
    run=authority.campaign/'start-1';req=ExperimentConfig.model_validate_json((run/'request.json').read_bytes())
    state,metadata=artifact.load_success(run,req,EVALUATION_HASH)
    assert metadata['training_commit']=='a'*40 and all(isinstance(t,torch.Tensor) for t in state.values())
    # Timeout ignores even a complete-looking child outcome and staged model.
    def timeout(*args,**kwargs):synthetic(*args,**kwargs);return 'timed_out',300.,-15
    monkeypatch.setattr(search_cli,'supervise',timeout)
    result=search_cli.run(raw(authority,2),authority)
    assert result['status']=='timed_out'
    run=authority.campaign/'start-2';req=ExperimentConfig.model_validate_json((run/'request.json').read_bytes())
    with pytest.raises(AdmissionError):artifact.load_success(run,req,EVALUATION_HASH)
    assert not (run/'model-artifact').exists()
    assert not torch.cuda.is_initialized()


def test_artifact_corruption_rejected(tmp_path):
    import torch
    from runner.model import small_cnn
    plan=SearchPlan.model_validate_json(json.dumps(example()))
    req=bind_request(plan,2,json.dumps({'learning_rate':.001,'weight_decay':.0001,'augmentation':'none'}),'a'*40,'worker-01','01_train')
    artifact.stage(small_cnn(),tmp_path,req,EVALUATION_HASH)
    (tmp_path/'.model-pending/state_dict.pt').write_bytes(b'corrupt')
    with pytest.raises(AdmissionError,match='hash'):artifact.publish_pending(tmp_path,req,EVALUATION_HASH)
    assert not (tmp_path/'model-artifact').exists()


def test_example_pair_caps_and_schema():
    plans=[SearchPlan.model_validate_json((ROOT/f'runner/plans/search-worker-0{n}.json').read_bytes()) for n in (1,2)]
    assert {p.worker_id for p in plans}=={'worker-01','worker-02'}
    assert all(p.status=='draft' and p.max_starts==6 for p in plans)
    assert all(sum(t.arm==arm for p in plans for t in p.trials)==6 for arm in ('random','ai'))
    assert json.loads((ROOT/'runner/plans/search-plan.schema.json').read_text())==SearchPlan.model_json_schema()
