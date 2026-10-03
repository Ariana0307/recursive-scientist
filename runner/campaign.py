"""Trusted, fixed G3 campaign authority. No paths/limits/commands from model input."""
import datetime
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess

from schemas.contracts import Config, ExperimentConfig, config_hash
from runner.storage import AdmissionError, atomic_new, json_new, lock, read_bytes, safe_dir

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / 'recursive-scientist-local'
CAMPAIGN_ID = 'RS-20261003-G3-r1-01-baseline'
METHOD = ROOT / 'runner/g3-method.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def paths():
    # Neither path is an argument to the scientific model interface.
    return PRIVATE / 'campaigns' / CAMPAIGN_ID, PRIVATE / 'campaign-authority' / CAMPAIGN_ID


def current_commit():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True).strip()
    if dirty:
        raise AdmissionError('campaign requires clean committed code')
    return commit


def policy():
    p = json.loads(read_bytes(METHOD))
    if p['campaign_id'] != CAMPAIGN_ID or p['max_starts'] != 3 or p['seeds'] != [42, 43, 44] or p['timeout_seconds'] != 300:
        raise AdmissionError('invalid fixed G3 policy')
    if p['evaluation_sha256'] != digest(read_bytes(ROOT / 'runner/evaluate.py')):
        raise AdmissionError('frozen evaluator hash mismatch')
    return p


def secure_location(path):
    for node in [path, *path.parents]:
        if node.is_symlink():
            raise AdmissionError('authority path symlink rejected')
        if node == PRIVATE:
            break
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise AdmissionError('authority must be owned and writable only by trusted operator')


def key():
    _, authority = paths()
    secure_location(authority)
    p = authority / 'signing.key'
    secure_location(p)
    if p.stat().st_mode & 0o077:
        raise AdmissionError('authority key permissions unsafe')
    return read_bytes(p)


def signed(payload):
    return {'payload': payload, 'hmac_sha256': hmac.new(key(), canonical(payload), hashlib.sha256).hexdigest()}


def verify(record):
    if set(record) != {'payload', 'hmac_sha256'} or not hmac.compare_digest(
            record['hmac_sha256'], hmac.new(key(), canonical(record['payload']), hashlib.sha256).hexdigest()):
        raise AdmissionError('authorization signature mismatch')
    return record['payload']


def expected_authority():
    return {'campaign_id': CAMPAIGN_ID, 'code_commit': current_commit(),
            'method_sha256': digest(read_bytes(METHOD)), 'policy': policy()}


def authorize():
    """Trusted-operator-only CLI, never exposed as a scientific agent tool."""
    expected = expected_authority()
    campaign, authority = paths()
    safe_dir(campaign.parent); safe_dir(authority.parent)
    # Exclusive creation. Missing/damaged historical authorization is never recreated.
    authority.mkdir(mode=0o700)
    campaign.mkdir(mode=0o700)
    atomic_new(authority / 'signing.key', secrets.token_bytes(32))
    record = signed(expected)
    json_new(authority / 'authorization.json', record)
    json_new(campaign / 'authorization.json', record)
    os.chmod(authority / 'signing.key', 0o400)
    os.chmod(authority / 'authorization.json', 0o400)
    os.chmod(campaign / 'authorization.json', 0o400)
    return expected


def load_authority():
    campaign, authority = paths()
    if not campaign.exists() or not authority.exists():
        raise AdmissionError('campaign not authorized')
    secure_location(campaign); secure_location(authority)
    original = read_bytes(authority / 'authorization.json')
    if original != read_bytes(campaign / 'authorization.json'):
        raise AdmissionError('authorization mirror mismatch')
    payload = verify(json.loads(original))
    if payload != expected_authority():
        raise AdmissionError('authorization no longer matches fixed committed policy')
    return payload


def slots():
    campaign, authority = paths()
    recorded = sorted(authority.glob('slot-*.json'))
    mirrors = sorted(campaign.glob('slot-*.json'))
    if [p.name for p in recorded] != [p.name for p in mirrors]:
        raise AdmissionError('reservation mirror missing; manual review required')
    out = []
    for i, path in enumerate(recorded, 1):
        if path.name != f'slot-{i}.json':
            raise AdmissionError('noncontiguous budget ledger')
        raw = read_bytes(path)
        if raw != read_bytes(campaign / path.name):
            raise AdmissionError('reservation mirror mismatch')
        item = verify(json.loads(raw))
        if item['slot'] != i or item['campaign_id'] != CAMPAIGN_ID:
            raise AdmissionError('invalid reservation identity')
        out.append(item)
    if len(out) > 3:
        raise AdmissionError('ledger already exceeds authorization')
    return out


def request_from_parameters(raw):
    cfg = Config.model_validate_json(raw)
    template = policy()['fixed_config']
    if cfg.seed not in [42, 43, 44] or cfg.model_dump(exclude={'seed'}) != template:
        raise AdmissionError('parameters outside the fixed G3 baseline authorization')
    base = json.loads(read_bytes(ROOT / 'configs/baseline.json'))
    base.update(config=cfg.model_dump(), seed=cfg.seed, status='approved',
                experiment_id=f'G3-r1-baseline-seed-{cfg.seed}', code_version=current_commit(), config_hash=config_hash(cfg))
    return ExperimentConfig.model_validate_json(json.dumps(base))


def reserve(request):
    """Hold trusted authority lock across admission; primary journal survives mirror failure."""
    campaign, authority = paths()
    load_authority()
    fd = lock(authority / 'budget.lock', blocking=True)
    try:
        auth = load_authority()
        prior = slots()
        if len(prior) >= 3:
            raise AdmissionError('G3 three-start budget exhausted')
        if prior and not (campaign / f'start-{len(prior)}' / 'result.json').is_file():
            raise AdmissionError('previous job active or orphaned; no concurrent launch')
        n = len(prior) + 1
        if request.seed != auth['policy']['seeds'][n - 1]:
            raise AdmissionError('seed order/retry not authorized')
        # Rebind the complete request at both sides, not just a config hash.
        expected = request_from_parameters(request.config.model_dump_json())
        if expected != request:
            raise AdmissionError('request identity differs from trusted approval')
        payload = {'campaign_id': CAMPAIGN_ID, 'slot': n, 'seed': request.seed,
                   'experiment_id': request.experiment_id, 'request_sha256': digest(request.model_dump_json().encode()),
                   'parent_pid': os.getpid(), 'code_commit': request.code_version,
                   'method_sha256': auth['method_sha256'], 'evaluation_sha256': auth['policy']['evaluation_sha256'],
                   'timeout_seconds': 300, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        receipt = signed(payload)
        json_new(authority / f'slot-{n}.json', receipt)
        json_new(campaign / f'slot-{n}.json', receipt)
        return payload
    finally:
        os.close(fd)


def sealed_capability(reservation):
    fd = os.memfd_create('rs-g3-trusted-dispatch', os.MFD_ALLOW_SEALING)
    os.write(fd, canonical(signed(reservation)))
    os.lseek(fd, 0, os.SEEK_SET)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
    return fd


def claim_child(fd):
    """Actual training entry needs a sealed inherited receipt AND the persistent slot."""
    seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    if seals & required != required:
        raise AdmissionError('unsealed child capability')
    os.lseek(fd, 0, os.SEEK_SET)
    receipt = verify(json.loads(os.read(fd, 16384)))
    campaign, authority = paths()
    auth = load_authority()
    locked = lock(authority / 'budget.lock', blocking=True)
    try:
        records = slots()
        n = receipt['slot']
        if not 1 <= n <= 3 or len(records) < n or records[n - 1] != receipt:
            raise AdmissionError('child slot not reserved')
        if receipt['parent_pid'] != os.getppid():
            raise AdmissionError('child not spawned by admitting parent')
        if receipt['method_sha256'] != auth['method_sha256']:
            raise AdmissionError('child method differs')
        attempt = campaign / f'start-{n}'
        req = ExperimentConfig.model_validate_json(read_bytes(attempt / 'request.json'))
        if req != request_from_parameters(req.config.model_dump_json()) or digest(req.model_dump_json().encode()) != receipt['request_sha256']:
            raise AdmissionError('child request mismatch')
        # Immutable primary one-use marker blocks replay even if the public mirror is removed.
        atomic_new(authority / f'claimed-{n}', b'claimed once before GPU initialization\n')
        atomic_new(attempt / 'child-started', b'authorized G3 child\n')
        return req, attempt, receipt
    finally:
        os.close(locked)
