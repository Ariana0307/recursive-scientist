"""Trusted CPU-only G5 draft compilation; never creates search authority."""
from pathlib import Path
from itertools import product
from hashlib import sha256
from datetime import datetime
import json
import numpy as np
import rfc8785
from runner.search_plan import SearchPlan, EVALUATION_HASH
from schemas.split import split_hash, SPLIT_ID

ROOT=Path(__file__).resolve().parents[1]
SPACE={'learning_rate':[.0003,.001,.003],'weight_decay':[0.,.0001,.001],'augmentation':['none','basic']}

def canonical_hash(obj):return sha256(rfc8785.dumps(obj)).hexdigest()

def random_catalog():
    # Ascending tuple order: augmentation string order is basic, then none.
    return [dict(zip(SPACE,values)) for values in sorted(product(*SPACE.values()))]

def freeze(timestamp):
    if np.__version__!='2.2.6':raise RuntimeError('requires frozen NumPy 2.2.6')
    catalog=random_catalog()
    permutation=np.random.Generator(np.random.PCG64(20261004)).permutation(18).tolist()
    draws=[{'round':i+1,'seed':42+i,'worker_id':'worker-01' if i%2==0 else 'worker-02',
            'catalog_index':index,'parameters':catalog[index]} for i,index in enumerate(permutation[:6])]
    random_doc={'task_id':'RS-20261004-G5','revision':'r1','status':'draft_no_authorization',
        'generated_at':timestamp,'numpy_version':np.__version__,'rng':'numpy.random.Generator(PCG64(20261004))',
        'algorithm':'permutation(18), first 6 indices, without replacement; one global list projected by round',
        'catalog_order':'ascending tuple (learning_rate, weight_decay, augmentation); numeric ascending; basic < none',
        'catalog':catalog,'full_permutation':permutation,'draws':draws,'list_hash_rfc8785':canonical_hash(draws)}
    plans={}
    for worker,role in [('worker-01','01_train'),('worker-02','02_deploy')]:
        trials=[]
        for i in range(6):
            random_worker='worker-01' if i%2==0 else 'worker-02'
            trials.append({'arm':'random' if worker==random_worker else 'ai','seed':42+i,
                           'random_parameters':draws[i]['parameters'] if worker==random_worker else None})
        obj={'plan_version':'1.0.0','status':'draft','campaign_id':'G5-r1-search-'+worker,'task_id':'RS-20261004-G5',
             'role':role,'worker_id':worker,'max_starts':6,'epochs':3,'batch_size':128,'split_seed':20261003,
             'split_id':SPLIT_ID,'split_indices_hash':split_hash(),'model':'small-cnn-v1','dataset':'cifar10-python-v1',
             'timeout_seconds':300,'evaluation_sha256':EVALUATION_HASH,'candidate_space':SPACE,'trials':trials}
        plans[worker]=SearchPlan.model_validate_json(json.dumps(obj))
    return random_doc,plans

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--timestamp',required=True);args=p.parse_args()
    timestamp=datetime.fromisoformat(args.timestamp)
    if timestamp.tzinfo is None:raise ValueError('timezone required')
    random_doc,plans=freeze(timestamp.isoformat())
    for worker,plan in plans.items():
        (ROOT/f'runner/plans/search-{worker}.json').write_text(plan.model_dump_json(indent=2)+'\n')
    dest=ROOT/'configs/g5';dest.mkdir(exist_ok=True)
    (dest/'random-global.json').write_text(json.dumps(random_doc,indent=2)+'\n')
    initial=json.loads((dest/'ai-initial-proposal.json').read_text())
    manifest={'task_id':'RS-20261004-G5','revision':'r1','status':'draft_no_authorization',
      'frozen_at':timestamp.isoformat(),'normalization':'RFC8785 via rfc8785 0.1.4; SHA256',
      'plan_hashes':{w:p.digest() for w,p in plans.items()},'global_random_hash':canonical_hash(random_doc),
      'random_list_hash':random_doc['list_hash_rfc8785'],'ai_initial_hash':canonical_hash(initial),
      'evaluation_sha256':EVALUATION_HASH,'total_max_starts':12,'strategy_max_starts':{'random':6,'ai':6},
      'ai_remaining_parameters':'undetermined; baseline and own completed history only',
      'authorization_created':False}
    manifest['freeze_hash']=canonical_hash(manifest)
    (dest/'freeze-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
