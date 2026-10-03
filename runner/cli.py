"""Launch with the private Python interpreter: python -I -B runner/cli.py ..."""
# -I removes inherited import paths. Add only this reviewed checkout, not user paths.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import argparse
import datetime
import json
import os
import signal
import time
import traceback

from schemas.contracts import ExperimentConfig, Result, match_result, retry_action
from runner.engine import PRIVATE, check_checkout, check_environment, child, preflight
from runner.storage import AdmissionError, atomic_new, digest, json_new, lock, read_bytes, reserve_quota, safe_dir
from runner.supervisor import supervise


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def result_payload(request, status, started, elapsed, device, metrics=None, error=None):
    r = request.model_dump(mode='json')
    r.update(status=status, validation={
        'split_id': request.validation.split_id,
        'split_indices_hash': request.validation.split_indices_hash,
        'metrics': metrics or {'accuracy': None, 'loss': None}},
        runtime={'elapsed_seconds': elapsed, 'started_at': started,
                 'finished_at': now(), 'actual_device': device}, error=error)
    result = Result.model_validate_json(json.dumps(r))
    match_result(request, result)
    return result


def run_request(raw, smoke=False):
    # Schema validation and approval always precede filesystem allocation or GPU imports.
    request = ExperimentConfig.model_validate_json(raw)
    check_checkout(request)
    check_environment()
    runs = PRIVATE / 'runs'
    safe_dir(runs)
    job = runs / request.experiment_id
    created = False
    try:
        job.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        safe_dir(job)
    try:
        fd = lock(job / 'lock')
    except BlockingIOError:
        existing = ExperimentConfig.model_validate_json(read_bytes(job / 'request.json'))
        retry_action(existing, request, 'running')
        return {'admission': 'in_progress', 'experiment_id': request.experiment_id}
    try:
        canonical = request.model_dump_json().encode()
        if created:
            atomic_new(job / 'request.json', canonical)
        else:
            try:
                existing = ExperimentConfig.model_validate_json(read_bytes(job / 'request.json'))
            except FileNotFoundError:
                raise AdmissionError('missing immutable request; manual review required')
            retry_action(existing, request, 'running')  # complete-envelope conflict check
        attempts = sorted(job.glob('attempt-*'))
        # Unknown entries or interrupted publication require review, never blind rerun.
        known = {'request.json', 'lock'} | {p.name for p in attempts}
        if any(p.name not in known for p in job.iterdir()):
            raise AdmissionError('unknown job state; manual review required')
        for n, previous in enumerate(attempts, 1):
            if previous.name != f'attempt-{n:04d}' or previous.is_symlink() or not previous.is_dir():
                raise AdmissionError('invalid attempt sequence; manual review required')
        if attempts:
            previous = attempts[-1]
            try:
                prior = Result.model_validate_json(read_bytes(previous / 'result.json'))
                match_result(request, prior)
            except FileNotFoundError:
                raise AdmissionError('unfinished attempt without active lock; manual review required')
            action = retry_action(request, request, prior.status)
            if action == 'reuse':
                return {'admission': 'reuse', 'attempt': previous.name, 'result': prior.model_dump(mode='json')}
        elif not created:
            raise AdmissionError('allocated ID without attempt; manual review required')
        attempt = job / f'attempt-{len(attempts) + 1:04d}'
        quota = reserve_quota(runs, request.experiment_id, attempt.name, digest(canonical))
        attempt.mkdir(mode=0o700)
        mode = 'smoke' if smoke else 'full'
        json_new(attempt / 'context.json', {'parent_pid': os.getpid(), 'mode': mode,
                 'request_sha256': digest(canonical), 'quota': quota})
        started, monotonic_start = now(), time.monotonic()
        status, metrics, error = 'failed', None, {'kind': 'execution', 'message': 'Job did not produce a valid completed outcome.'}
        device = None
        json_new(attempt / 'started.json', {'started_at': started, 'mode': mode,
                                           'timeout_seconds': request.config.timeout_seconds})
        try:
            env = os.environ.copy()
            env.pop('PYTHONPATH', None)
            env.pop('PYTHONHOME', None)
            env.update(CUBLAS_WORKSPACE_CONFIG=':4096:8', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
            with (attempt / 'worker.log').open('xb') as logfile:
                remaining = max(0, request.config.timeout_seconds - (time.monotonic() - monotonic_start))
                state, _, exit_code = supervise([sys.executable, '-I', '-B', str(ROOT / 'runner/cli.py'),
                                '_child', str(attempt)], remaining, logfile, env)
            if state == 'timed_out' or time.monotonic() - monotonic_start >= request.config.timeout_seconds:
                status, error = 'timed_out', {'kind': 'timeout', 'message': 'Job process group exceeded its hard wall-clock deadline.'}
            elif exit_code == 0:
                outcome = json.loads(read_bytes(attempt / 'outcome.json'))
                status, metrics, error = outcome['status'], outcome['metrics'], outcome['error']
            else:
                error = {'kind': 'execution', 'message': f'Job exited with code {exit_code}; private attempt log retains the original error.'}
        except (KeyboardInterrupt, SystemExit):
            status, error = 'cancelled', {'kind': 'cancelled', 'message': 'Operator cancelled the supervised job.'}
        except Exception as exc:
            atomic_new(attempt / 'supervisor-error.txt', traceback.format_exc().encode())
            status, error = 'failed', {'kind': 'execution', 'message': f'Supervisor error ({type(exc).__name__}); attempt retained.'}
        elapsed = time.monotonic() - monotonic_start
        if (attempt / 'device.json').exists():
            device = json.loads(read_bytes(attempt / 'device.json'))['actual_device']
        if status == 'succeeded' and elapsed >= request.config.timeout_seconds:
            status, metrics, error = 'timed_out', None, {'kind': 'timeout', 'message': 'Completion exceeded the hard deadline.'}
        if status != 'succeeded':
            metrics = None
        try:
            result = result_payload(request, status, started, elapsed, device, metrics, error)
        except Exception:
            result = result_payload(request, 'failed', started, elapsed, device,
                         error={'kind': 'execution', 'message': 'Child outcome failed shared Result validation; evidence retained.'})
        atomic_new(attempt / 'result.json', result.model_dump_json(indent=2).encode())
        return {'admission': 'executed', 'attempt': attempt.name, 'result': result.model_dump(mode='json')}
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('preflight')
    run = sub.add_parser('run')
    run.add_argument('request', type=Path, help='trusted operator path to approved JSON; paths are not config fields')
    run.add_argument('--smoke', action='store_true', help='128/64 diagnostic; returns cancelled/null metrics, consumes one G1 slot')
    internal = sub.add_parser('_child', help=argparse.SUPPRESS)
    internal.add_argument('attempt', type=Path)
    args = parser.parse_args()
    if args.command == '_child':
        expected = PRIVATE / 'runs'
        attempt = args.attempt
        if attempt.is_symlink() or attempt.parent.parent != expected:
            raise AdmissionError('invalid private child path')
        child(attempt)
        return 0
    if args.command == 'preflight':
        print(json.dumps(preflight(), indent=2))
        return 0
    def cancel(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    result = run_request(read_bytes(args.request), args.smoke)
    print(json.dumps(result, indent=2))
    return 0 if result.get('admission') in ('reuse', 'in_progress') or result.get('result', {}).get('status') == 'succeeded' else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Avoid reflecting untrusted config values or local paths into public output.
        print(json.dumps({'admission': 'rejected', 'error_type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, AdmissionError) else 'Validation/environment/job failure; no unvalidated request executed.'}), file=sys.stderr)
        raise SystemExit(1)
