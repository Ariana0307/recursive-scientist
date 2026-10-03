"""Deterministic, append-only best-so-far and frozen three-seed statistics."""
import json
import os
import statistics
from schemas.contracts import ExperimentConfig, Result, match_result
from runner import campaign as budget
from runner.storage import AdmissionError, json_new, lock, read_bytes


def records():
    budget.load_authority()
    campaign, _ = budget.paths()
    out = []
    for slot in budget.slots():
        attempt = campaign / f"start-{slot['slot']}"
        if not (attempt / 'result.json').exists():
            out.append((slot, None))
            continue
        request = ExperimentConfig.model_validate_json(read_bytes(attempt / 'request.json'))
        result = Result.model_validate_json(read_bytes(attempt / 'result.json'))
        match_result(request, result)
        if budget.digest(request.model_dump_json().encode()) != slot['request_sha256']:
            raise AdmissionError('summary request differs from reservation')
        if result.code_version != slot['code_commit'] or result.seed != slot['seed']:
            raise AdmissionError('summary code/seed differs')
        out.append((slot, result))
    return out


def update_best():
    campaign, authority = budget.paths()
    fd = lock(authority / 'best.lock', blocking=True)
    try:
        all_records = records()
        snapshots = sorted(campaign.glob('best-*.json'))
        incumbent = None
        if snapshots:
            incumbent = json.loads(read_bytes(snapshots[-1]))
            known = {slot['slot']: result for slot, result in all_records}
            r = known.get(incumbent['slot'])
            if r is None or r.status != 'succeeded' or r.validation.metrics.accuracy != incumbent['accuracy']:
                raise AdmissionError('best history differs from validated results')
        for slot, result in all_records:
            if result is None or result.status != 'succeeded':continue
            score = result.validation.metrics.accuracy
            if incumbent is None or score > incumbent['accuracy']:
                incumbent = {'slot': slot['slot'], 'seed': result.seed, 'experiment_id': result.experiment_id,
                             'accuracy': score, 'code_commit': result.code_version,
                             'rule': 'strict accuracy improvement only; ties retain earlier slot'}
                json_new(campaign / f'best-{len(snapshots)+1:03d}.json', incumbent)
                snapshots.append(None)
        return incumbent
    finally:
        os.close(fd)


def summary():
    observed = records()
    rows = [{'slot': slot['slot'], 'seed': slot['seed'], 'status': result.status if result else 'unknown',
             'accuracy': result.validation.metrics.accuracy if result else None,
             'loss': result.validation.metrics.loss if result else None,
             'elapsed_seconds': result.runtime.elapsed_seconds if result else None} for slot, result in observed]
    complete = len(rows) == 3 and [r['seed'] for r in rows] == [42, 43, 44] and all(r['status'] == 'succeeded' for r in rows)
    values = [r['accuracy'] for r in rows] if complete else []
    sigma = statistics.stdev(values) if complete else None
    return {'task_id': 'RS-20261003-G3', 'revision': 'r1', 'campaign_id': budget.CAMPAIGN_ID,
            'code_commit': budget.current_commit(), 'starts_used': len(rows), 'starts_limit': 3,
            'observations': rows, 'complete_three_seed_baseline': complete,
            'mean_accuracy': statistics.mean(values) if complete else None,
            'sample_sigma_ddof1': sigma, 'exploratory_two_sigma': 2*sigma if sigma is not None else None,
            'interpretation': '2*sigma is exploratory noise only, not a significance test; G1 pilot excluded.',
            'best_so_far': update_best()}
