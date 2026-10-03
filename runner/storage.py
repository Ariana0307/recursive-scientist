"""Private append-only artifacts, advisory locks, and persistent G1 quota."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


class AdmissionError(RuntimeError):
    pass


def safe_dir(path: Path):
    # Reject symlinks at every existing ancestor, not merely the final component.
    for part in (path, *path.parents):
        if part.is_symlink():
            raise AdmissionError('symlink in private directory path')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise AdmissionError('private path is not a directory')


def read_bytes(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        return stream.read()


def atomic_new(path: Path, data: bytes):
    """Publish complete file with link(2), which cannot replace an existing name."""
    safe_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, path, follow_symlinks=False)
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        os.unlink(tmp)


def json_new(path, value):
    atomic_new(path, (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())


def lock(path: Path, blocking=False):
    safe_dir(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BaseException:
        os.close(fd)
        raise
    return fd


def reserve_quota(runs: Path, experiment_id, attempt, request_digest):
    """Append-only two-slot ledger. Reservations survive crashes and consume quota."""
    ledger = runs / '.g1-quota'
    fd = lock(ledger / 'lock', blocking=True)
    try:
        known = {'lock', 'slot-1.json', 'slot-2.json'}
        if any(p.name not in known for p in ledger.iterdir()):
            raise AdmissionError('unknown quota state; manual review required')
        occupied = []
        for n in (1, 2):
            p = ledger / f'slot-{n}.json'
            if p.exists() or p.is_symlink():
                record = json.loads(read_bytes(p))
                if record.get('slot') != n or record.get('task_id') != 'RS-20261003-G1':
                    raise AdmissionError('invalid quota ledger; manual review required')
                occupied.append(n)
        if occupied == [2]:
            raise AdmissionError('quota gap; manual review required')
        if len(occupied) >= 2:
            raise AdmissionError('G1 total GPU attempt quota exhausted')
        slot = len(occupied) + 1
        record = dict(task_id='RS-20261003-G1', slot=slot, experiment_id=experiment_id,
                      attempt=attempt, request_sha256=request_digest)
        json_new(ledger / f'slot-{slot}.json', record)
        return record
    finally:
        os.close(fd)


def digest(data):
    return hashlib.sha256(data).hexdigest()
