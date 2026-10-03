"""CPU-only G3 authorization/locking/equivalence tests; outcomes here are synthetic."""
import ast
import copy
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import textwrap

import pytest
from runner import campaign as budget
from runner import campaign_cli, campaign_summary
from runner.cli import result_payload
from runner.storage import AdmissionError, atomic_new, json_new

BASE = '4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8'


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, 'PRIVATE', tmp_path)
    monkeypatch.setattr(budget, 'current_commit', lambda: 'a'*40)
    return tmp_path


def params(seed=42):
    return json.dumps(dict(budget.policy()['fixed_config'], seed=seed))


def close_slot(receipt, status='failed', accuracy=None):
    path = budget.paths()[0] / f"start-{receipt['slot']}"
    path.mkdir(exist_ok=True)
    req = budget.request_from_parameters(params(receipt['seed']))
    if not (path/'request.json').exists(): atomic_new(path/'request.json', req.model_dump_json().encode())
    result = result_payload(req, status, '2026-10-03T00:00:00Z', 1.0, 'cuda',
                            {'accuracy':accuracy,'loss':1.0} if status=='succeeded' else None,
                            None if status=='succeeded' else {'kind':'execution','message':'synthetic test only'})
    atomic_new(path/'result.json',result.model_dump_json().encode())
    return path


def test_unauthorized_and_operator_exclusive(isolated):
    with pytest.raises(AdmissionError, match='not authorized'):budget.load_authority()
    budget.authorize()
    with pytest.raises(FileExistsError):budget.authorize()
    assert budget.load_authority()['policy']['max_starts']==3


@pytest.mark.parametrize('key,value',[('campaign','evil'),('path','/tmp/evil'),('command','anything'),('max_starts',999)])
def test_model_cannot_supply_control_fields(isolated,key,value):
    obj=json.loads(params());obj[key]=value
    with pytest.raises(ValueError):budget.request_from_parameters(json.dumps(obj))


@pytest.mark.parametrize('field,value',[('seed',45),('epochs',1),('timeout_seconds',299),('learning_rate',0.003)])
def test_baseline_allowlist(isolated,field,value):
    obj=json.loads(params());obj[field]=value
    with pytest.raises(AdmissionError):budget.request_from_parameters(json.dumps(obj))


def test_tampered_authorization_and_evaluator(isolated,monkeypatch):
    budget.authorize();campaign,authority=budget.paths()
    p=campaign/'authorization.json';p.chmod(0o600)
    original=p.read_bytes();changed=json.loads(original);changed['payload']['policy']['max_starts']=9
    p.write_text(json.dumps(changed))
    with pytest.raises(AdmissionError,match='mirror'):budget.load_authority()
    # Even matching two altered copies cannot create a valid signature.
    q=authority/'authorization.json';q.chmod(0o600);q.write_bytes(p.read_bytes())
    with pytest.raises(AdmissionError,match='signature'):budget.load_authority()
    p.write_bytes(original);q.write_bytes(original)
    p.chmod(0o400);q.chmod(0o400)
    monkeypatch.setattr(budget,'current_commit',lambda:'b'*40)
    with pytest.raises(AdmissionError,match='committed policy'):budget.load_authority()


def test_failure_cancel_and_spawn_error_consume_slots(isolated,monkeypatch):
    budget.authorize()
    monkeypatch.setattr(campaign_cli,'check_checkout',lambda r:None)
    monkeypatch.setattr(campaign_cli,'check_environment',lambda:{})
    def failed(*a,**kw):raise OSError('synthetic start failure')
    monkeypatch.setattr(campaign_cli,'supervise',failed)
    first=campaign_cli.run_parameters(params(42));assert first['status']=='failed'
    def cancelled(*a,**kw):raise KeyboardInterrupt
    monkeypatch.setattr(campaign_cli,'supervise',cancelled)
    second=campaign_cli.run_parameters(params(43));assert second['status']=='cancelled'
    third=campaign_cli.run_parameters(params(44));assert third['status']=='cancelled'
    assert len(budget.slots())==3
    with pytest.raises(AdmissionError,match='exhausted'):campaign_cli.run_parameters(params(44))
    assert len(budget.slots())==3


def test_child_authorization_one_use_and_tampering(isolated,monkeypatch):
    budget.authorize();req=budget.request_from_parameters(params())
    slot=budget.reserve(req);attempt=budget.paths()[0]/'start-1';attempt.mkdir()
    atomic_new(attempt/'request.json',req.model_dump_json().encode())
    fd=budget.sealed_capability(slot)
    monkeypatch.setattr(budget.os,'getppid',lambda:os.getpid())
    try:
        r,path,receipt=budget.claim_child(fd);assert r==req and receipt==slot
        with pytest.raises(FileExistsError):budget.claim_child(fd)
    finally:os.close(fd)
    # A forged unsigned/seal-free descriptor is refused before any torch import.
    fd=os.memfd_create('synthetic',os.MFD_ALLOW_SEALING);os.write(fd,b'{}')
    try:
        with pytest.raises(AdmissionError,match='unsealed'):budget.claim_child(fd)
    finally:os.close(fd)


def test_child_rechecks_authority_after_reservation(isolated,monkeypatch):
    budget.authorize();req=budget.request_from_parameters(params());slot=budget.reserve(req)
    path=budget.paths()[0]/'start-1';path.mkdir();atomic_new(path/'request.json',req.model_dump_json().encode())
    fd=budget.sealed_capability(slot)
    p=budget.paths()[0]/'authorization.json';p.chmod(0o600);p.write_text('{}')
    try:
        with pytest.raises(AdmissionError):budget.claim_child(fd)
        assert not (budget.paths()[1]/'claimed-1').exists()
    finally:os.close(fd)


def test_orphan_mirror_loss_and_legacy_unchanged(isolated):
    legacy=isolated/'runs/.g1-quota';legacy.mkdir(parents=True)
    (legacy/'slot-1.json').write_text('old1');(legacy/'slot-2.json').write_text('old2')
    before={p.name:p.read_bytes() for p in legacy.iterdir()}
    budget.authorize();slot=budget.reserve(budget.request_from_parameters(params()))
    with pytest.raises(AdmissionError,match='orphaned'):budget.reserve(budget.request_from_parameters(params(43)))
    (budget.paths()[0]/'slot-1.json').unlink()
    with pytest.raises(AdmissionError,match='mirror missing'):budget.slots()
    assert before=={p.name:p.read_bytes() for p in legacy.iterdir()}


def test_concurrent_last_slot_and_restart(isolated):
    budget.authorize()
    for seed in (42,43):close_slot(budget.reserve(budget.request_from_parameters(params(seed))))
    ctx=multiprocessing.get_context('fork');queue=ctx.Queue()
    def race():
        try:budget.reserve(budget.request_from_parameters(params(44)));queue.put('reserved')
        except AdmissionError:queue.put('rejected')
    workers=[ctx.Process(target=race) for _ in range(8)]
    for p in workers:p.start()
    for p in workers:p.join(10);assert p.exitcode==0
    values=[queue.get(timeout=1) for _ in workers]
    assert values.count('reserved')==1 and values.count('rejected')==7
    assert len(budget.slots())==3
    another=ctx.Process(target=race);another.start();another.join(10)
    assert queue.get(timeout=1)=='rejected'


def test_best_never_regresses_and_sigma(isolated):
    budget.authorize()
    for seed,score in [(42,0.7),(43,0.6),(44,0.8)]:
        close_slot(budget.reserve(budget.request_from_parameters(params(seed))), 'succeeded', score)
        campaign_summary.update_best()
    best=list(budget.paths()[0].glob('best-*.json'));assert len(best)==2
    assert json.loads(best[0].read_text())['accuracy']==0.7
    s=campaign_summary.summary();assert s['mean_accuracy']==pytest.approx(0.7)
    assert s['sample_sigma_ddof1']==pytest.approx(0.1)
    assert s['exploratory_two_sigma']==pytest.approx(0.2)
    assert s['best_so_far']['accuracy']==0.8
    assert len(list(budget.paths()[0].glob('best-*.json')))==2


def test_failed_seed_no_three_seed_sigma(isolated):
    budget.authorize()
    for seed in (42,43,44):close_slot(budget.reserve(budget.request_from_parameters(params(seed))))
    s=campaign_summary.summary()
    assert s['mean_accuracy'] is None and s['sample_sigma_ddof1'] is None


def original_evaluation_body():
    old=subprocess.check_output(['git','show',BASE+':runner/engine.py'],cwd=budget.ROOT,text=True)
    return textwrap.dedent(old[old.index('    model.eval()\n'):old.index('    torch.cuda.synchronize()\n')])


def test_evaluation_structural_equivalence():
    old=ast.parse(original_evaluation_body())
    class BatchName(ast.NodeTransformer):
        def visit_Attribute(self,node):
            if ast.unparse(node)=='request.config.batch_size':return ast.copy_location(ast.Name(id='batch_size',ctx=ast.Load()),node)
            return self.generic_visit(node)
    old=BatchName().visit(old)
    new=ast.parse((budget.ROOT/'runner/evaluate.py').read_text())
    fun=next(n for n in new.body if isinstance(n,ast.FunctionDef))
    class RemoveEvidence(ast.NodeTransformer):
        def visit_If(self,node):
            if ast.unparse(node.test)=='evidence is not None':return None
            return self.generic_visit(node)
    body=RemoveEvidence().visit(ast.Module(body=fun.body[:-1],type_ignores=[]))
    assert ast.dump(old,include_attributes=False)==ast.dump(body,include_attributes=False)
    assert hashlib.sha256((budget.ROOT/'runner/evaluate.py').read_bytes()).hexdigest()==budget.policy()['evaluation_sha256']


def test_evaluation_numeric_equivalence_cpu():
    import torch
    from types import SimpleNamespace
    from runner.evaluate import evaluate
    from runner.model import preprocess,small_cnn
    torch.set_num_threads(2);torch.manual_seed(42)
    x=torch.randint(0,256,(19,3,32,32),dtype=torch.uint8);y=torch.arange(19)%10
    model=small_cnn();ids=torch.arange(19);generator=torch.Generator().manual_seed(42)
    criterion=torch.nn.CrossEntropyLoss(reduction='mean')
    namespace=dict(torch=torch,model=model,x=x,y=y,val_ids=ids,device=torch.device('cpu'),generator=generator,
                   preprocess=preprocess,criterion=criterion,request=SimpleNamespace(config=SimpleNamespace(batch_size=8)))
    # Only trusted, versioned G1 source is executed in this equivalence test.
    exec(compile(original_evaluation_body(),'<frozen-G1-evaluation>','exec'),namespace)
    rows=[];new=evaluate(model,x,y,ids,8,torch.device('cpu'),generator,criterion,rows)
    assert new==(namespace['correct'],namespace['loss_sum'],namespace['count'])
    assert len(rows)==19 and sum(t==p for _,t,p in rows)==new[0]
    assert not torch.cuda.is_initialized()
