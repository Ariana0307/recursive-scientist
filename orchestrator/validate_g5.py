"""Read-only G5 frozen-input check; safe for both workers before future approval."""
from pathlib import Path
import json,hashlib
from orchestrator.freeze_g5 import ROOT,freeze,canonical_hash
from runner.search_plan import SearchPlan,EVALUATION_HASH

def validate(root=ROOT):
    root=Path(root);manifest=json.loads((root/'configs/g5/freeze-manifest.json').read_text())
    assert manifest['status']=='draft_no_authorization' and not manifest['authorization_created']
    digest=manifest.pop('freeze_hash');assert canonical_hash(manifest)==digest
    expected_random,expected_plans=freeze(manifest['frozen_at'])
    random=json.loads((root/'configs/g5/random-global.json').read_text());assert random==expected_random
    assert canonical_hash(random)==manifest['global_random_hash']
    assert canonical_hash(random['draws'])==manifest['random_list_hash']
    for worker,p in expected_plans.items():
        current=SearchPlan.model_validate_json((root/f'runner/plans/search-{worker}.json').read_bytes())
        assert current==p and current.digest()==manifest['plan_hashes'][worker]
    initial=json.loads((root/'configs/g5/ai-initial-proposal.json').read_text())
    assert canonical_hash(initial)==manifest['ai_initial_hash']
    assert (initial['round'],initial['seed'],initial['worker_id'],initial['role'])==(1,42,'worker-02','02_deploy')
    assert initial['parameters']=={'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}
    assert hashlib.sha256((root/'runner/evaluate.py').read_bytes()).hexdigest()==EVALUATION_HASH
    return {'status':'passed_draft_only','freeze_hash':digest,'plan_hashes':manifest['plan_hashes'],
            'random_list_hash':manifest['random_list_hash'],'authorization_created':False,'training_starts':0}
if __name__=='__main__':print(json.dumps(validate(),indent=2))
