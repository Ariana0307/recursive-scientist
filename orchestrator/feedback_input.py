"""Trusted round-2 ingestion in the existing contract environment; no network."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,hashlib,json,subprocess
from pathlib import Path
from orchestrator.ai_history import verified_record,snapshot
from runner.search_plan import SearchPlan,bind_request
from runner.storage import read_bytes
ROOT=Path(__file__).resolve().parents[1]
RETURNED=Path.home()/'recursive-scientist-local/g6-return/worker-02/start-1'
BASELINE_HASHES={'42': ['e42bd0c2aad70773084caba8ee1a9b04f82a16597c080008bbf5710668b7260a', '15a983a85b0458d6437c752cf339636cceb5d4ad982576a820dca5210e5a7542'], '43': ['8bcff590eecb3141502d1b59123beb2eb5be747897d79e0c626a482074ade2ab', '9990a5c08c2d0443a9de4dbc398f135c673bd9eba28a426a1896d3a3fec6b9c6'], '44': ['007795e682709d63e303c1444f624ba3dc285481bf02fc634a1fbf3d3c22810c', 'de0df831a67ec91b7e4efd9bfb468a98010a592c5dc61fad34a8ff421c85d754']}

def ingest(request_hash,result_hash):
    records=[]
    for seed in (42,43,44):
        q=read_bytes(ROOT/f'configs/g6/baseline/seed-{seed}-request.json')
        r=read_bytes(ROOT/f'configs/g6/baseline/seed-{seed}-result.json')
        records.append(verified_record(q,r,*BASELINE_HASHES[str(seed)],origin='baseline'))
    plan=SearchPlan.model_validate_json(read_bytes(ROOT/'runner/plans/search-worker-02.json'))
    freeze=json.loads(read_bytes(ROOT/'configs/g5/freeze-manifest.json'))
    if plan.digest()!=freeze['plan_hashes']['worker-02']:raise ValueError('frozen AI plan mismatch')
    # Trusted operator copies actual returned files, and supplies reviewed byte hashes.
    # Missing results fail before any SDK construction or request reservation.
    q=read_bytes(RETURNED/'request.json');r=read_bytes(RETURNED/'result.json')
    from runner.campaign import current_commit
    commit=current_commit()
    expected=bind_request(plan,1,json.dumps({'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}),commit,'worker-02','02_deploy')
    from schemas.contracts import ExperimentConfig
    if ExperimentConfig.model_validate_json(q)!=expected:raise ValueError('returned request is not historical AI slot 1 at released code')
    records.append(verified_record(q,r,request_hash,result_hash,origin='ai',round_number=1,plan=plan,code_commit=commit))
    return snapshot(records,2)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request-sha256',required=True);p.add_argument('--result-sha256',required=True)
    a=p.parse_args();print(json.dumps(ingest(a.request_sha256,a.result_sha256),sort_keys=True))
if __name__=='__main__':main()
