"""Declared Omnigent server-side read tool. No shell or credentials exposed."""
from pathlib import Path
import json,time,datetime
ROOT=Path('/srv/research/historical-run')
def read_evidence(path: str) -> str:
 start=time.monotonic();p=Path(path).resolve();error=None
 try:
  if not any(p.is_relative_to(x) for x in (ROOT,ROOT.parent.parent/'RS-20261004-G10/r1')):raise ValueError('outside evidence allowlist')
  if not p.is_file() or p.suffix not in {'.json','.jsonl','.md','.txt','.csv','.yaml','.py'} or p.stat().st_size>150000:raise ValueError('small allowed text only')
  # Exclude runtime/private agent internals even under evidence root.
  if any(x in {'.codex-tmp','artifacts'} for x in p.parts):raise ValueError('private runtime excluded')
  result=p.read_text()
 except Exception as e:error=str(e);result=json.dumps({'error':error})
 with (ROOT/'evidence/omnigent/evidence-tool-events.jsonl').open('a') as f:f.write(json.dumps({'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tool':'read_evidence','path':str(p),'returned':result,'error':error,'elapsed_seconds':time.monotonic()-start})+'\n')
 return result
