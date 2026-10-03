"""Trusted G3 operator launcher. Model-facing input is Config JSON on stdin only."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import argparse
import json
import os
import signal
import time
import traceback
from runner import campaign as budget
from runner.cli import now, result_payload
from runner.engine import check_checkout, check_environment, train_job
from runner.storage import AdmissionError, atomic_new, json_new, read_bytes
from runner.supervisor import supervise


def run_parameters(raw):
    budget.load_authority()
    request = budget.request_from_parameters(raw)
    check_checkout(request)
    check_environment()
    reservation = budget.reserve(request)
    campaign, _ = budget.paths()
    attempt = campaign / f"start-{reservation['slot']}"
    attempt.mkdir(mode=0o700)
    atomic_new(attempt / 'request.json', request.model_dump_json(indent=2).encode())
    # Persist canonical resolved config as an additional audit artifact.
    atomic_new(attempt / 'config.json', request.config.model_dump_json(indent=2).encode())
    started, start = now(), time.monotonic()
    json_new(attempt / 'started.json', {'started_at': started, 'reservation': reservation})
    status, metrics, device = 'failed', None, None
    error = {'kind': 'execution', 'message': 'G3 job did not yield a complete result.'}
    capfd = None
    try:
        # Re-check immediately before passing the capability into the fixed child.
        budget.load_authority()
        capfd = budget.sealed_capability(reservation)
        env = os.environ.copy()
        env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        env.update(RS_G3_CAP_FD=str(capfd), CUBLAS_WORKSPACE_CONFIG=':4096:8', PYTHONDONTWRITEBYTECODE='1')
        with (attempt / 'worker.log').open('xb') as log:
            state, _, code = supervise([sys.executable, '-I', '-B', str(ROOT / 'runner/campaign_cli.py'), '_child'],
                       max(0, 300 - (time.monotonic() - start)), log, env, pass_fds=(capfd,))
        if state == 'timed_out' or time.monotonic() - start >= 300:
            status, error = 'timed_out', {'kind': 'timeout', 'message': 'G3 job exceeded its 300 second hard deadline.'}
        elif code == 0:
            outcome = json.loads(read_bytes(attempt / 'outcome.json'))
            status, metrics, error = outcome['status'], outcome['metrics'], outcome['error']
        else:
            error = {'kind': 'execution', 'message': f'G3 child exited with code {code}; original private log retained.'}
    except (KeyboardInterrupt, SystemExit):
        status, error = 'cancelled', {'kind': 'cancelled', 'message': 'Trusted operator cancelled the G3 attempt.'}
    except Exception as exc:
        atomic_new(attempt / 'supervisor-error.txt', traceback.format_exc().encode())
        error = {'kind': 'execution', 'message': f'G3 supervisor failure ({type(exc).__name__}); reservation consumed.'}
    finally:
        if capfd is not None:
            os.close(capfd)
    elapsed = time.monotonic() - start
    if (attempt / 'device.json').exists():
        device = json.loads(read_bytes(attempt / 'device.json'))['actual_device']
    if status == 'succeeded' and elapsed >= 300:
        status, metrics, error = 'timed_out', None, {'kind': 'timeout', 'message': 'G3 completion after deadline.'}
    if status != 'succeeded':
        metrics = None
    try:
        result = result_payload(request, status, started, elapsed, device, metrics, error)
    except Exception:
        result = result_payload(request, 'failed', started, elapsed, device,
                        error={'kind': 'execution', 'message': 'G3 child outcome rejected by shared validator.'})
    atomic_new(attempt / 'result.json', result.model_dump_json(indent=2).encode())
    from runner.campaign_summary import update_best
    update_best()
    return result.model_dump(mode='json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['authorize', 'run', 'summary', '_child'])
    args = parser.parse_args()
    if args.action == 'authorize':
        check_environment()
        print(json.dumps(budget.authorize(), indent=2))
    elif args.action == '_child':
        request, attempt, receipt = budget.claim_child(int(os.environ['RS_G3_CAP_FD']))
        check_checkout(request)
        packages = check_environment()
        context = {'mode': 'full', 'campaign_id': budget.CAMPAIGN_ID,
                   'evaluation_sha256': receipt['evaluation_sha256']}
        train_job(request, packages, attempt, context)
    elif args.action == 'summary':
        from runner.campaign_summary import summary
        print(json.dumps(summary(), indent=2))
    else:
        def cancel(signum, frame): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)
        # Bounded, closed JSON Config; no experiment IDs, paths, campaigns or commands.
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384: raise AdmissionError('parameter payload too large')
        result = run_parameters(raw)
        print(json.dumps(result, indent=2))
        return 0 if result['status'] == 'succeeded' else 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'rejected', 'error_type': type(exc).__name__,
                          'message': str(exc) if isinstance(exc, AdmissionError) else 'G3 authorization/input error; no arbitrary command executed.'}), file=sys.stderr)
        raise SystemExit(1)
