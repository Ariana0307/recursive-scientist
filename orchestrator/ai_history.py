"""Trusted ingestion in the pinned contract environment; no model or training calls."""
from hashlib import sha256
import json
from schemas.contracts import ExperimentConfig, Result, match_result
from runner.search_plan import SearchPlan

BASELINE_COMMIT='931049af15ddafa12a5163e924a3ea84bbfbbf3f'

def verified_record(request_bytes,result_bytes,expected_request_hash,expected_result_hash,*,origin,round_number=0,plan=None,code_commit=None):
    if origin not in ('baseline','ai'):raise ValueError('Random and test evidence are not AI-visible')
    if sha256(request_bytes).hexdigest()!=expected_request_hash or sha256(result_bytes).hexdigest()!=expected_result_hash:
        raise ValueError('source hash mismatch')
    q=ExperimentConfig.model_validate_json(request_bytes);r=Result.model_validate_json(result_bytes);match_result(q,r)
    if r.config.epochs!=3 or r.config.batch_size!=128:raise ValueError('wrong comparison protocol')
    if origin=='baseline':
        if round_number!=0 or r.code_version!=BASELINE_COMMIT or r.seed not in (42,43,44):raise ValueError('wrong baseline identity')
        if (r.config.learning_rate,r.config.weight_decay,r.config.augmentation)!=(.001,.0001,'none'):raise ValueError('wrong baseline configuration')
        if r.status!='succeeded':raise ValueError('complete baseline required')
    else:
        if not isinstance(plan,SearchPlan) or not 1<=round_number<=6:raise ValueError('trusted AI plan slot required')
        slot=plan.trials[round_number-1]
        if slot.arm!='ai' or r.seed!=slot.seed or r.experiment_id!=f'{plan.campaign_id}-s{round_number}' or r.code_version!=code_commit:
            raise ValueError('result is not bound to the trusted AI slot')
    return {'origin':origin,'round':round_number,'experiment_id':r.experiment_id,'seed':r.seed,
       'parameters':{k:getattr(r.config,k) for k in ('learning_rate','weight_decay','augmentation')},
       'status':r.status,'accuracy':r.validation.metrics.accuracy,'loss':r.validation.metrics.loss,
       'code_version':r.code_version,'config_hash':r.config_hash,
       'request_sha256':expected_request_hash,'result_sha256':expected_result_hash}

def snapshot(records,current_round):
    if any(r['origin']=='ai' and r['round']>=current_round for r in records):raise ValueError('future evidence excluded')
    if sorted(r['seed'] for r in records if r['origin']=='baseline')!=[42,43,44]:raise ValueError('three baseline seeds required')
    if sorted(r['round'] for r in records if r['origin']=='ai')!=list(range(1,current_round)):raise ValueError('all prior AI terminal outcomes required')
    return {'schema_version':'ai-visible-v1','current_round':current_round,'records':records,
            'verification':'full_contract_request_result_hash_split','random_visible':False}
