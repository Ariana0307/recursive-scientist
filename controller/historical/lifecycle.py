"""Durable bounded controller primitives. No inference or external action at import."""
from pathlib import Path
import json,time,datetime,os,fcntl,signal,subprocess
class Stopped(RuntimeError): pass
class Store:
 def __init__(self,root):self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
 def read(self,name,default=None):
  p=self.root/name
  return json.loads(p.read_text()) if p.exists() else default
 def write(self,name,value):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.tmp')
  with t.open('w') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(t,p)
 def event(self,phase,conclusion,*,agent='lead',session='unknown',round_id='preflight',experiment_id=None,evidence_path=None,type='transition',**data):
  path=self.root/'events.jsonl'
  with (self.root/'events.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   n=sum(1 for _ in path.open())+1 if path.exists() else 1
   e={'run_id':'RS-20261004-G11-r1','round_id':round_id,'event_id':f'event-{n:06d}','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'agent':agent,'session':session,'phase':phase,'experiment_id':experiment_id,'evidence_path':evidence_path,'conclusion':conclusion,'type':type,'data':data}
   with path.open('a') as f:f.write(json.dumps(e,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
  return e
 def stopped(self):return (self.root/'stop_requested.json').exists()
 def request_stop(self,reason='user'):
  if not self.stopped():self.write('stop_requested.json',{'timestamp':time.time(),'reason':reason})
  s=self.read('state.json',{});s.update(status='stopping',stop={'requested':True,'remote_confirmed':False,'detail':'Stop intent persisted; waiting for owned remote task confirmation.'});self.write('state.json',s)
 def reserve(self,job):
  with (self.root/'jobs.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if self.stopped():raise Stopped('persistent stop blocks new dispatch')
   p=self.root/'jobs'/f'{job}.json'
   if p.exists():return False
   self.write('jobs/'+job+'.json',{'job_id':job,'status':'reserved','created':time.time()});return True
 def finish(self,job,result):self.write('jobs/'+job+'.json',{'job_id':job,'status':'completed','result':result,'finished':time.time()})
 def save_best(self,observed,accepted,metric_version):self.write('best.json',{'metric_version':metric_version,'best_observed':observed,'best_accepted':accepted,'updated':time.time()})
 def finalize(self,status,confirmed,reason):
  if status=='stopped' and not confirmed:status='stopping'
  s=self.read('state.json',{});s.update(status=status,updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),stop={'requested':self.stopped(),'remote_confirmed':confirmed,'detail':reason});self.write('state.json',s)

def owned_start(argv,log,cwd=None):
 with open(log,'ab') as f:p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=f,stderr=f,cwd=cwd,start_new_session=True)
 stat=Path('/proc')/str(p.pid)/'stat'
 return {'pid':p.pid,'pgid':p.pid,'start_ticks':stat.read_text().split()[21]}
def alive(owner):
 p=Path('/proc')/str(owner['pid'])/'stat'
 return p.exists() and p.read_text().split()[21]==owner['start_ticks'] and p.read_text().split()[2]!='Z'
def cancel_owned(owner):
 if alive(owner):os.killpg(owner['pgid'],signal.SIGTERM)
 deadline=time.monotonic()+2
 while alive(owner) and time.monotonic()<deadline:time.sleep(.02)
 if alive(owner):os.killpg(owner['pgid'],signal.SIGKILL)
 return not alive(owner)
