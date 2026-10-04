"""Bounded evidence read adapter, adapted from the recorded integration."""
import json
from pathlib import Path
from runtime_config import CONFIG

def read_evidence(path: str) -> str:
    root = Path(CONFIG['run_root']).resolve()
    p = Path(path).resolve()
    try:
        if not p.is_relative_to(root):
            raise ValueError('outside run evidence root')
        if any(x in {'private-runtime', '.codex-tmp', 'artifacts', '.ssh'} for x in p.parts):
            raise ValueError('private runtime excluded')
        if p.suffix not in {'.json', '.jsonl', '.md', '.txt', '.csv', '.yaml', '.py'} or p.stat().st_size > 150000:
            raise ValueError('small text evidence only')
        return p.read_text()
    except (ValueError, OSError) as error:
        return json.dumps({'error': str(error)})
