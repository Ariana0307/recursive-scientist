"""Public installed Omnigent CodexExecutor: real persistent two-role orchestration.
Server /v1/sessions attempt remains in omnigent_server_attempt.py; not claimed working.
"""
import asyncio,dataclasses,datetime,json,os,time,pathlib
from omnigent import CodexExecutor,ExecutorConfig,TextChunk,ExecutorError,TurnComplete
from omnigent.spec.types import RetryPolicy
from evidence_tools import read_evidence
from runtime_config import CONFIG, require_execution
ROOT=pathlib.Path(CONFIG['run_root']).resolve()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def serial(x):
 if dataclasses.is_dataclass(x):return dataclasses.asdict(x)
 if hasattr(x,'model_dump'):return x.model_dump(mode='json')
 return str(x)
class OmnigentTeam:
 def __init__(self,root=ROOT,timeout=180):
  self.root=pathlib.Path(root);self.out=self.root/'evidence/omnigent';self.out.mkdir(parents=True,exist_ok=True);self.timeout=timeout
  self.count=max([int(p.name.split('-')[0]) for p in self.out.glob('*-*.result.json') if p.name.split('-')[0].isdigit()]+[0]);self.executors={};self.messages={}
 def log(self,kind,**kw):
  with (self.out/'events.jsonl').open('a') as f:f.write(json.dumps({'timestamp':now(),'kind':kind,**kw},default=serial,ensure_ascii=False)+'\n')
 async def __aenter__(self):
  require_execution()
  os.environ['HARNESS_CODEX_MINIMAL_CONFIG']='true';os.environ['OPENAI_AGENTS_DISABLE_TRACING']='1';os.environ['OMNIGENT_DATA_DIR']=str(self.out/'private-runtime')
  for role in ('researcher','reviewer'):
   e=CodexExecutor(cwd=str(self.root),codex_path=CONFIG['codex_binary'],model_provider_override='openai',enable_web_search=False,disable_native_tools=True,retry_policy=RetryPolicy(max_retries=0,timeout_per_request_s=self.timeout),agent_name=CONFIG['run_id']+'_'+role,skills_filter='none')
   e._tool_executor=lambda name,args:read_evidence(**args) if name=='read_evidence' else (_ for _ in ()).throw(ValueError('tool not allowed'))
   self.executors[role]=e;self.messages[role]=[]
  self.log('local_team_created',interface='public omnigent.CodexExecutor',roles=['researcher','reviewer'],server_session_path='blocked: runner not bound; not used for scientific turns')
  return self
 async def turn(self,role,prompt,upstream=None):
  if (self.root/'control/stop_requested.json').exists():raise RuntimeError('persistent stop')
  self.count+=1;cid=f'{self.count:02d}-{role}';key=CONFIG['run_id']+'-'+role;e=self.executors[role];self.messages[role].append({'role':'user','content':prompt,'session_id':key})
  (self.out/(cid+'.prompt.txt')).write_text(prompt);self.log('handoff_submit',call_id=cid,role=role,upstream=upstream,session_key=key)
  tools=[{'name':'read_evidence','description':'Read a small allowed research evidence text file; no shell or credentials.','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}}]
  system='You are the independent Codex '+role+' in Recursive Scientist. Qwen is the research subject, not a researcher. Use the provided evidence tool. Do not spawn agents, run experiments, access credentials or request user approval. Investigate, judge and propose within the stated finite scope. Return the requested JSON only; preserve uncertainty.'
  text=[];errs=[];complete=[];start=time.monotonic()
  try:
   async with asyncio.timeout(self.timeout):
    async for ev in e.run_turn(self.messages[role],tools,system,ExecutorConfig(extra={})):
     self.log('omnigent_executor_event',call_id=cid,role=role,event_type=type(ev).__name__,event=serial(ev))
     if isinstance(ev,TextChunk):text.append(ev.text)
     if isinstance(ev,ExecutorError):errs.append(ev.message)
     if isinstance(ev,TurnComplete):complete.append(serial(ev))
     if (self.root/'control/stop_requested.json').exists():await e.interrupt_session(key);raise RuntimeError('user stop while Codex running')
  except BaseException as exc:
   try:await e.interrupt_session(key)
   except Exception:pass
   errs.append(repr(exc))
  identities=[]
  for session_key,s in e._session_states.items():
   app=s.app_session
   if app:
    proc=getattr(app,'_proc',None)
    identities.append({'omnigent_session_key':session_key,'codex_thread_id':app.thread_id,'codex_turn_id':app.active_turn_id,'pid':getattr(proc,'pid',None)})
  thread=identities[0]['codex_thread_id'] if identities else 'unknown'
  result={'call_id':cid,'role':role,'text':''.join(text),'response_id':cid,'session_id':thread,'conversation_id':thread,'identities':identities,'elapsed_seconds':time.monotonic()-start,'status':'completed' if complete and not errs else 'failed','errors':errs,'turn_complete':complete,'interface':'omnigent.CodexExecutor','upstream':upstream}
  (self.out/(cid+'.result.json')).write_text(json.dumps(result,default=serial,indent=2));self.log('handoff_return',**result)
  if result['status']!='completed':raise RuntimeError('Codex turn failed: '+str(errs))
  self.messages[role].append({'role':'assistant','content':result['text'],'session_id':key});return result
 async def __aexit__(self,*args):
  for role,e in self.executors.items():await e.close();self.log('executor_closed',role=role)
