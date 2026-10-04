"""G6 synthetic temporary authority only. Never invokes a GPU or real launcher."""
import json,os,shutil,multiprocessing
from pathlib import Path
import pytest
from runner import search_authority as mod
from runner.search_plan import SearchPlan
from runner.storage import AdmissionError,atomic_new
from runner.cli import result_payload
ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(params=['worker-01','worker-02'])
def a(tmp_path,monkeypatch,request):
    p=SearchPlan.model_validate_json((ROOT/f'runner/plans/search-{request.param}.json').read_bytes())
    monkeypatch.setattr(mod.legacy,'current_commit',lambda:'a'*40)
    obj=mod.SearchAuthority(p,p.worker_id,p.role,tmp_path/'SYNTHETIC-private')
    obj.authorize(operator='SYNTHETIC operator',reason='temporary CPU regression fixture')
    return obj

def params(a,n=1):
    t=a.plan.trials[n-1]
    return t.random_parameters.model_dump_json() if t.random_parameters else json.dumps({'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'})

def terminal(a):
    q,r=a.reserve(params(a));p=a.campaign/'start-1';p.mkdir()
    atomic_new(p/'request.json',q.model_dump_json().encode())
    result=result_payload(q,'failed','2026-10-04T00:00:00Z',1.,None,None,{'kind':'execution','message':'SYNTHETIC'})
    atomic_new(p/'result.json',result.model_dump_json().encode())
    return q,r

def test_slot_one_restart_and_extension(a):
    assert a.plan.max_starts==6 and a.plan.status=='draft' and a.released_through()==1
    terminal(a)
    restarted=mod.SearchAuthority(a.plan,a.worker_id,a.role,a.private)
    with pytest.raises(AdmissionError,match='not explicitly released'):restarted.reserve(params(a,2))
    with pytest.raises(AdmissionError):a.extend_release(2,operator='',reason='bad')
    a.extend_release(2,operator='trusted human',reason='explicit reviewed continuation')
    assert a.released_through()==2
    a.reserve(params(a,2))
    with pytest.raises(AdmissionError,match='not explicitly released'):a.reserve(params(a,3))
    record=a.mirrored('release-02.json');assert record['operator']=='trusted human' and record['previous_slot']==1

def test_deleted_both_slot_ledgers_cannot_reset(a):
    terminal(a)
    for root in (a.campaign,a.authority):(root/'slot-1.json').unlink()
    with pytest.raises(AdmissionError,match='fence'):a.reserve(params(a))

def test_deleted_campaigns_cannot_reauthorize(a):
    shutil.rmtree(a.campaign);shutil.rmtree(a.authority)
    with pytest.raises(FileExistsError):a.authorize(operator='synthetic',reason='must fail')

def test_campaign_change_or_release_tamper_rejected(a):
    changed=a.plan.model_copy(update={'campaign_id':'attempted-reset'})
    b=mod.SearchAuthority(changed,a.worker_id,a.role,a.private)
    with pytest.raises(AdmissionError,match='frozen'):b.authorize(operator='synthetic',reason='must fail')
    for root in (a.fence,a.authority,a.campaign):
        p=root/'release-01.json';d=json.loads(p.read_bytes());d['payload']['through_slot']=6;p.write_text(json.dumps(d))
    with pytest.raises(AdmissionError,match='signature'):a.load()

def test_concurrent_reserve_has_only_one_winner(a):
    def job():
        try:a.reserve(params(a));os._exit(0)
        except AdmissionError:os._exit(3)
    children=[multiprocessing.get_context('fork').Process(target=job) for _ in range(4)]
    for p in children:p.start()
    for p in children:p.join(5);assert not p.is_alive()
    assert sorted(p.exitcode for p in children)==[0,3,3,3]
    assert len(a.slots())==1

def test_child_one_use_and_no_replay(a,monkeypatch):
    q,r=terminal(a);fd=a.capability(r)
    monkeypatch.setattr(mod.os,'getppid',lambda:r['parent_pid'])
    try:
        a.claim(fd)
        # Erasing historical claimed marker still cannot erase independent fence.
        (a.authority/'claimed-1').unlink()
        with pytest.raises(FileExistsError):a.claim(fd)
    finally:os.close(fd)

def test_preserves_first_ai(a):
    if a.worker_id=='worker-02':
        with pytest.raises(AdmissionError,match='historical'):a.reserve(json.dumps({'learning_rate':.001,'weight_decay':.0001,'augmentation':'none'}))
        assert a.slots()==[]

def test_legacy_direct_calls_deny_before_mutation():
    from runner import cli,engine,campaign
    for fn,args in [(cli.run_request,(b'{}',)),(engine.child,(Path('/nonexistent'),)),(campaign.authorize,()),(campaign.reserve,(None,)),(campaign.claim_child,(-1,))]:
        with pytest.raises(AdmissionError,match='legacy execution disabled'):fn(*args)

def test_missing_release_mirror_and_unsigned_increase_denied(a):
    (a.campaign/'release-01.json').unlink()
    with pytest.raises(AdmissionError,match='mirror'):a.reserve(params(a))
    assert a.slots()==[]

def test_existing_worker_interpreter_selection(tmp_path,monkeypatch):
    from runner import worker_entry
    python=tmp_path/'existing/bin/python';python.parent.mkdir(parents=True);python.write_text('SYNTHETIC')
    class Result:returncode=0
    monkeypatch.setattr(worker_entry.subprocess,'run',lambda *args,**kw:Result())
    assert worker_entry.select_python(str(python))==str(python)
    with pytest.raises(RuntimeError,match='absolute'):worker_entry.select_python('relative/python')
    with pytest.raises(RuntimeError,match='exactly one'):worker_entry.select_python(str(tmp_path/'absent'))
