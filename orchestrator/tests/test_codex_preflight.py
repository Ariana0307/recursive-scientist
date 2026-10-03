"""Local safety tests; no model requests or credentials."""
from pathlib import Path
import pytest
from orchestrator.codex_preflight import allocate_attempt


def test_fresh_attempt_and_no_overwrite(tmp_path):
    requested = tmp_path / 'RS-20261003-G2-new'
    assert allocate_attempt(requested, tmp_path) == requested
    evidence = requested / 'record.json'
    evidence.write_text('original')
    with pytest.raises(FileExistsError):
        allocate_attempt(requested, tmp_path)
    assert evidence.read_text() == 'original'


def test_reject_g1_and_outside_root(tmp_path):
    for requested in [tmp_path / 'RS-20261003-G1-old', tmp_path.parent / 'RS-20261003-G2-outside']:
        with pytest.raises(ValueError):
            allocate_attempt(requested, tmp_path)
        assert not requested.exists()


def test_reject_symlinked_root(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    linked = tmp_path / 'linked'
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        allocate_attempt(linked / 'RS-20261003-G2-new', linked)
    assert list(real.iterdir()) == []
