"""Synthetic contract-validated ingestion tests, not experiment evidence."""
import json,hashlib
from pathlib import Path
import pytest
from schemas.contracts import ExperimentConfig,Result,config_hash,Config
from runner.search_plan import SearchPlan,bind_request
from orchestrator.ai_history import verified_record,snapshot
from orchestrator.freeze_g5 import ROOT

def hashes(q,r):return hashlib.sha256(q).hexdigest(),hashlib.sha256(r).hexdigest()
def ai_pair(worker,n,status='succeeded'):
 p=SearchPlan.model_validate_json((ROOT/f'runner/plans/search-{worker}.json').read_bytes())
 t=p.trials[n-1];params=t.random_parameters.model_dump() if t.arm=='random' else {'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}
 q=bind_request(p,n,json.dumps(params),'c'*40,p.worker_id,p.role)
 r=q.model_dump(mode='json');r['status']=status;r['validation'].pop('metric');r['validation'].pop('objective')
 r['validation']['metrics']={'accuracy':.5,'loss':1.} if status=='succeeded' else {'accuracy':None,'loss':None}
 r['runtime']={'elapsed_seconds':1.,'started_at':'2026-10-04T00:00:00Z','finished_at':'2026-10-04T00:00:01Z','actual_device':'cuda'}
 r['error']=None if status=='succeeded' else {'kind':'timeout','message':'SYNTHETIC CPU fixture only'}
 return p,q.model_dump_json().encode(),Result.model_validate_json(json.dumps(r)).model_dump_json().encode()

def test_verified_ai_source_and_failed_terminal_metrics():
 for state in ('succeeded','timed_out'):
  p,q,r=ai_pair('worker-02',1,state)
  row=verified_record(q,r,*hashes(q,r),origin='ai',round_number=1,plan=p,code_commit='c'*40)
  assert row['status']==state
  assert row['accuracy']==(.5 if state=='succeeded' else None)

def test_random_label_and_plan_arm_cannot_cross_boundary():
 p,q,r=ai_pair('worker-01',1)
 with pytest.raises(ValueError,match='Random'):verified_record(q,r,*hashes(q,r),origin='random',round_number=1,plan=p,code_commit='c'*40)
 with pytest.raises(ValueError,match='AI slot'):verified_record(q,r,*hashes(q,r),origin='ai',round_number=1,plan=p,code_commit='c'*40)

def test_corrupted_source_and_wrong_code_rejected():
 p,q,r=ai_pair('worker-02',1)
 with pytest.raises(ValueError,match='hash'):verified_record(q,r,'0'*64,hashes(q,r)[1],origin='ai',round_number=1,plan=p,code_commit='c'*40)
 with pytest.raises(ValueError,match='AI slot'):verified_record(q,r,*hashes(q,r),origin='ai',round_number=1,plan=p,code_commit='d'*40)
