"""CPU-only regression tests; all fabricated outcomes are synthetic test fixtures."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from schemas.contracts import Config, ExperimentConfig, config_hash
from runner import cli
from runner.data import load_training
from runner.storage import AdmissionError, atomic_new, json_new, lock, reserve_quota, safe_dir
from runner.supervisor import supervise

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def payload():
    value = json.loads((ROOT / 'configs/baseline.json').read_text())
    value.update(status='approved', code_version='a' * 40, experiment_id='synthetic-test')
    return value


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'PRIVATE', tmp_path)
    monkeypatch.setattr(cli, 'check_checkout', lambda r: None)
    monkeypatch.setattr(cli, 'check_environment', lambda: {})
    return tmp_path


def execute_fixture(monkeypatch, status='succeeded'):
    calls = []
    def synthetic(command, timeout, log, env):
        path = Path(command[-1]); calls.append(path)
        json_new(path / 'device.json', {'actual_device': 'cuda'})
        json_new(path / 'outcome.json', {'status': status,
            'metrics': {'accuracy': 0.1, 'loss': 2.3} if status == 'succeeded' else {'accuracy': None, 'loss': None},
            'error': None if status == 'succeeded' else {'kind': 'execution', 'message': 'synthetic failure fixture'}})
        return 'finished', 0.0, 0
    monkeypatch.setattr(cli, 'supervise', synthetic)
    return calls


def test_success_cache_conflicts_and_tampered_cache(isolated, payload, monkeypatch):
    calls = execute_fixture(monkeypatch)
    first = cli.run_request(json.dumps(payload))
    assert first['result']['status'] == 'succeeded'
    assert cli.run_request(json.dumps(payload))['admission'] == 'reuse'
    assert len(calls) == 1
    for field in ('code_version', 'config'):
        changed = copy.deepcopy(payload)
        if field == 'code_version': changed[field] = 'b' * 40
        else:
            changed['config']['learning_rate'] = 0.002
            changed['config_hash'] = config_hash(Config.model_validate(changed['config']))
        with pytest.raises(ValueError, match='conflict'):
            cli.run_request(json.dumps(changed))
    # Cached outcomes cannot bypass match_result.
    path = calls[0] / 'result.json'
    altered = json.loads(path.read_text()); altered['code_version'] = 'c' * 40
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='code_version'):
        cli.run_request(json.dumps(payload))
    assert len(calls) == 1


def test_append_only_retry_and_global_quota(isolated, payload, monkeypatch):
    calls = execute_fixture(monkeypatch, 'failed')
    first = cli.run_request(json.dumps(payload)); old = (calls[0] / 'result.json').read_bytes()
    second = cli.run_request(json.dumps(payload))
    assert first['attempt'] == 'attempt-0001' and second['attempt'] == 'attempt-0002'
    assert (calls[0] / 'result.json').read_bytes() == old
    with pytest.raises(AdmissionError, match='quota exhausted'):
        cli.run_request(json.dumps(payload))
    payload['experiment_id'] = 'other-id'
    with pytest.raises(AdmissionError, match='quota exhausted'):
        cli.run_request(json.dumps(payload))
    assert len(calls) == 2


def test_timeout_ignores_late_success(isolated, payload, monkeypatch):
    def late(command, timeout, log, env):
        path = Path(command[-1])
        json_new(path / 'outcome.json', {'status': 'succeeded', 'metrics': {'accuracy': 0.9, 'loss': 0.1}, 'error': None})
        return 'timed_out', timeout, -15
    monkeypatch.setattr(cli, 'supervise', late)
    r = cli.run_request(json.dumps(payload))['result']
    assert r['status'] == 'timed_out' and r['error']['kind'] == 'timeout'
    assert r['validation']['metrics'] == {'accuracy': None, 'loss': None}


def test_cancel_and_spawn_failure_terminal(isolated, payload, monkeypatch):
    def cancelled(*args): raise KeyboardInterrupt
    monkeypatch.setattr(cli, 'supervise', cancelled)
    first = cli.run_request(json.dumps(payload))['result']
    assert first['status'] == 'cancelled' and first['validation']['metrics']['accuracy'] is None
    def failed(*args): raise OSError('synthetic spawn failure')
    monkeypatch.setattr(cli, 'supervise', failed)
    second = cli.run_request(json.dumps(payload))['result']
    assert second['status'] == 'failed'


def test_lock_and_orphan_require_no_execution(isolated, payload, monkeypatch):
    job = isolated / 'runs' / payload['experiment_id']; safe_dir(job)
    atomic_new(job / 'request.json', ExperimentConfig.model_validate_json(json.dumps(payload)).model_dump_json().encode())
    fd = lock(job / 'lock')
    try:
        assert cli.run_request(json.dumps(payload))['admission'] == 'in_progress'
    finally: os.close(fd)
    (job / 'attempt-0001').mkdir()
    with pytest.raises(AdmissionError, match='manual review'):
        cli.run_request(json.dumps(payload))
    assert not (isolated / 'runs/.g1-quota').exists()


def test_invalid_config_before_allocation(isolated, payload):
    payload['experiment_id'] = '../escape'
    with pytest.raises(ValueError): cli.run_request(json.dumps(payload))
    assert not (isolated / 'runs').exists()


def test_real_proposal_and_dirty_code_rejected(payload, monkeypatch):
    from runner.engine import check_checkout
    payload['status'] = 'proposed'
    monkeypatch.setattr('runner.engine.subprocess.check_output', lambda cmd, **kw: 'a' * 40 if 'rev-parse' in cmd else '')
    with pytest.raises(ValueError, match='not authorized'):
        check_checkout(ExperimentConfig.model_validate_json(json.dumps(payload)))
    payload['status'] = 'approved'
    monkeypatch.setattr('runner.engine.subprocess.check_output', lambda cmd, **kw: 'a' * 40 if 'rev-parse' in cmd else ' M runner/cli.py')
    with pytest.raises(RuntimeError, match='clean'):
        check_checkout(ExperimentConfig.model_validate_json(json.dumps(payload)))


def test_atomic_no_overwrite_and_symlinks(tmp_path):
    target = tmp_path / 'record'
    atomic_new(target, b'original')
    with pytest.raises(FileExistsError): atomic_new(target, b'changed')
    assert target.read_bytes() == b'original'
    real = tmp_path / 'real'; real.mkdir()
    link = tmp_path / 'link'; link.symlink_to(real, target_is_directory=True)
    with pytest.raises(AdmissionError, match='symlink'): safe_dir(link / 'child')
    assert not (real / 'child').exists()


def test_archive_verified_before_deserialize(tmp_path, monkeypatch):
    archive = tmp_path / 'cifar.tar.gz'; archive.write_bytes(b'not the official archive')
    called = []
    monkeypatch.setattr('runner.data.pickle.load', lambda *args, **kw: called.append(True))
    with pytest.raises(ValueError, match='MD5'): load_training(archive)
    assert not called


def test_deadline_leaves_unrelated_process_alive(tmp_path):
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
    try:
        with (tmp_path / 'log').open('wb') as log:
            state, elapsed, code = supervise([sys.executable, '-c', 'import time; time.sleep(30)'], 0.15, log, os.environ.copy())
        assert state == 'timed_out' and elapsed < 3 and code != 0
        assert unrelated.poll() is None
    finally:
        unrelated.terminate(); unrelated.wait()


def test_quota_persists_across_processes(tmp_path):
    reserve_quota(tmp_path, 'one', 'attempt-0001', 'a' * 64)
    reserve_quota(tmp_path, 'two', 'attempt-0001', 'b' * 64)
    script = 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from runner.storage import reserve_quota; reserve_quota(Path(sys.argv[2]),"three","attempt-0001","c"*64)'
    proc = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(ROOT), str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode != 0 and 'quota exhausted' in proc.stderr


def test_model_and_rng_cpu():
    import torch
    from runner.model import small_cnn, preprocess
    torch.set_num_threads(2); torch.manual_seed(42)
    model = small_cnn()
    x = torch.arange(3 * 32 * 32, dtype=torch.int64).remainder(256).to(torch.uint8).reshape(1, 3, 32, 32)
    a = preprocess(x, 'basic', torch.Generator().manual_seed(42))
    b = preprocess(x, 'basic', torch.Generator().manual_seed(42))
    assert torch.equal(a, b) and a.shape == x.shape
    assert a.min() >= -1 and a.max() <= 1
    assert model(a).shape == (1, 10)
    assert sum(p.numel() for p in model.parameters()) == 545098
    assert not torch.cuda.is_initialized()
