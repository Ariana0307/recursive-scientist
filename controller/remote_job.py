"""Bounded remote owner, fixed argv, durable stop, no duplicate dispatch."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,fcntl
from runtime_config import CONFIG, require_execution
ROOT=Path(CONFIG['remote_root']);ROOT.mkdir(parents=True,exist_ok=True)
def write(p,x):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(x,indent=2));os.replace(t,p)
def alive(o):
 p=Path('/proc')/str(o['pid'])/'stat'
 return p.exists() and p.read_text().split()[21]==o['start_ticks'] and p.read_text().split()[2]!='Z'
def status(batch):
 p=ROOT/'runs'/batch/'owner.json'
 o=json.loads(p.read_text()) if p.exists() else None
 return {'batch':batch,'owner':o,'running':bool(o and alive(o)),'stop_requested':(ROOT/'STOP').exists(),'completed':(ROOT/'runs'/batch/'completed.json').exists(),'partial':(ROOT/'runs'/batch/'evaluation.partial.json').exists(),'requests':len(list((ROOT/'ledger').glob('request-*.json')))}
def main():
 action,batch=sys.argv[1:3];assert batch in ('batch-1','batch-2')
 if action != 'status':require_execution()
 p=ROOT/'runs'/batch;p.mkdir(parents=True,exist_ok=True)
 with (ROOT/'dispatch.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  if action=='start':
   if (ROOT/'STOP').exists():raise RuntimeError('persistent stop')
   if (p/'owner.json').exists():print(json.dumps(status(batch)));return
   if batch=='batch-2' and not (ROOT/'runs/batch-1/completed.json').exists():raise RuntimeError('prior batch not confirmed completed')
   # Each of at most two batches gets <=600sec, so combined <=1200sec.
   argv=['timeout','--signal=TERM','--kill-after=3','597',CONFIG['remote_python'],'-B',str(ROOT/'qwen_batch.py'),str(p)]
   with (p/'execution.log').open('ab') as log:c=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
   write(p/'owner.json',{'pid':c.pid,'pgid':c.pid,'start_ticks':(Path('/proc')/str(c.pid)/'stat').read_text().split()[21],'started':time.time(),'argv':argv,'wall_limit_seconds':600})
  elif action=='stop':
   write(ROOT/'STOP',{'requested_epoch':time.time()})
   for b in ('batch-1','batch-2'):
    op=ROOT/'runs'/b/'owner.json'
    if op.exists():
     o=json.loads(op.read_text())
     if alive(o):os.killpg(o['pgid'],signal.SIGTERM)
   deadline=time.monotonic()+2
   while time.monotonic()<deadline and any(status(b)['running'] for b in ('batch-1','batch-2')):time.sleep(.05)
   for b in ('batch-1','batch-2'):
    x=status(b)
    if x['running']:os.killpg(x['owner']['pgid'],signal.SIGKILL)
  elif action!='status':raise ValueError(action)
 print(json.dumps(status(batch)))
if __name__=='__main__':main()
