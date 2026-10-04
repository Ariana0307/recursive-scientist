"""Trusted operator approval entry; never exposed to a research Agent."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json
from runner.search_authority import SearchAuthority,PLAN_FILES,PRIVATE
from runner.storage import json_new,read_bytes,AdmissionError
from runner.search_plan import SearchPlan

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['authorize-first','extend'])
    p.add_argument('--worker',required=True,choices=['worker-01','worker-02'])
    p.add_argument('--operator',required=True);p.add_argument('--reason',required=True)
    p.add_argument('--through-slot',type=int,required=True)
    a=p.parse_args()
    if not a.operator.strip() or not a.reason.strip():raise AdmissionError('operator/reason required')
    plan=SearchPlan.model_validate_json(read_bytes(PLAN_FILES[a.worker]))
    authority=SearchAuthority(plan,plan.worker_id,plan.role)
    authority.frozen_identity();authority.expected()
    binding={'worker_id':plan.worker_id,'role':plan.role};path=PRIVATE/'search-worker-binding.json'
    if a.action=='authorize-first':
        if a.through_slot!=1:raise AdmissionError('first production approval is slot 1 only')
        if path.exists():
            if SearchAuthority.local().worker_id!=a.worker:raise AdmissionError('existing worker binding conflict')
        else:
            json_new(path,binding);path.chmod(0o600)
        authority.authorize(operator=a.operator,reason=a.reason)
    else:
        if SearchAuthority.local().worker_id!=a.worker:raise AdmissionError('worker binding conflict')
        authority.extend_release(a.through_slot,operator=a.operator,reason=a.reason)
    print(json.dumps({'worker':a.worker,'plan_hash':plan.digest(),'released_through':authority.released_through()}))
if __name__=='__main__':main()
