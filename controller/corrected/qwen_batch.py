"""G14: real Omnigent one-step execution, append-only HTTP reservations, no retries."""
import os,sys,json,time,asyncio,hashlib,fcntl,socket
from runtime_config import CONFIG, require_execution
from pathlib import Path
from decimal import Decimal
ROOT=Path(sys.argv[1]); LEDGER=ROOT.parent.parent/'ledger'; LEDGER.mkdir(exist_ok=True); os.environ.update(OPENAI_AGENTS_DISABLE_TRACING='1',OTEL_SDK_DISABLED='true',OMNIGENT_DATA_DIR=str(ROOT/'sdk-state'))
import httpx
from openai import AsyncOpenAI
import omnigent.inner.openai_agents_sdk_executor as sdk
from omnigent.inner.executor import ExecutorConfig,TextChunk,ExecutorError
from omnigent.spec.types import RetryPolicy
sdk._EMPTY_TURN_MAX_ATTEMPTS=1
MODEL=CONFIG['model']
def save(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
def load(p):return json.loads(p.read_text())
class RawStream(httpx.AsyncByteStream):
 def __init__(self,stream,path,owner):self.stream,self.path,self.owner=stream,path,owner
 async def __aiter__(self):
  try:
   with self.path.open('xb') as f:
    async for b in self.stream:f.write(b);f.flush();yield b
  except Exception as e:
   self.owner.infrastructure_error=type(e).__name__
   save(self.path.with_suffix('.stream-error.json'),{'error_type':type(e).__name__,'message':str(e)})
   raise
 async def aclose(self):await self.stream.aclose()
class Transport(httpx.AsyncBaseTransport):
 def __init__(self,case,schema):self.case,self.schema=case,schema;self.sent=False;self.inner=httpx.AsyncHTTPTransport(retries=0,trust_env=False);self.infrastructure_error=None
 async def handle_async_request(self,req):
  if self.sent:raise RuntimeError('One-step boundary: no second HTTP request authorized')
  if (ROOT.parent.parent/'STOP').exists():raise RuntimeError('User stop marker')
  assert str(req.url)==CONFIG['model_base_url'].rstrip('/')+'/chat/completions'
  body=json.loads(await req.aread());assert body['model']==MODEL
  body['temperature']=0;body['stream_options']={'include_usage':True}
  if self.schema:body['response_format']={'type':'json_schema','json_schema':{'name':'answer','strict':True,'schema':self.schema}}
  assert body['max_tokens']==2048 and body['reasoning_effort']=='none'
  if os.environ.get('G14_CAPTURE_ONLY')=='1':
   save(ROOT/'payloads'/f'{self.case}.json',body)
   raise RuntimeError('OFFLINE_CAPTURE_ONLY_NO_HTTP_SENT')
  require_execution()
  preview=load(ROOT/'payloads'/f'{self.case}.json')
  assert body==preview, 'Actual SDK request differs from pre-reviewed frozen payload'
  ledger=LEDGER
  with (LEDGER/'budget.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   n=len(list(ledger.glob('request-*.json')))+1
   if n>12:raise RuntimeError('12-request cap')
   payload=json.dumps(body).encode();save(ledger/f'request-{n:02}.json',{'number':n,'case':self.case,'epoch':time.time(),'payload':body,'sha256':hashlib.sha256(payload).hexdigest()})
   self.sent=True;self.response_file=ledger/f'response-{n:02}.raw'
  headers=dict(req.headers);headers.pop('content-length',None)
  outgoing=httpx.Request(req.method,req.url,headers=headers,content=payload,extensions=req.extensions)
  t=time.monotonic()
  try:
   res=await self.inner.handle_async_request(outgoing)
   save(ledger/f'http-{n:02}.json',{'status':res.status_code,'headers_elapsed_seconds':time.monotonic()-t})
   if res.status_code>=400:self.infrastructure_error='HTTP_'+str(res.status_code)
   return httpx.Response(res.status_code,headers=res.headers,stream=RawStream(res.stream,ledger/f'response-{n:02}.raw',self),extensions=res.extensions)
  except Exception as e:
   self.infrastructure_error=type(e).__name__;save(ledger/f'error-{n:02}.json',{'type':type(e).__name__,'message':str(e),'elapsed_seconds':time.monotonic()-t});raise
 async def aclose(self):await self.inner.aclose()
def schema(kind):
 props={'explanation':{'type':'string'}}
 if kind=='numeric':props.update(winner={'type':'string','enum':['current','reference','tie']},delta_pp={'type':'number'})
 else:props.update(verdict={'type':'string','enum':['established','not_established']})
 return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}
TOOLS=[{'name':'read_record','description':'Read one immutable test record by ID. No files, network or writes.','parameters':{'type':'object','properties':{'record_id':{'type':'string'}},'required':['record_id'],'additionalProperties':False}}, {'name':'compare_decimal','description':'Compare two exact finite decimal strings. Pure calculation with no side effects.','parameters':{'type':'object','properties':{'left':{'type':'string'},'right':{'type':'string'}},'required':['left','right'],'additionalProperties':False}}]
async def case(test,arm,conf):
 key=ROOT.name+'-'+test['id']+'-'+arm;case_dir=ROOT/'cases'/key;case_dir.mkdir(parents=True,exist_ok=False)
 calls=[];start=time.monotonic();errors=[];events=[];text=''
 def dispatch(name,args):
  t=time.monotonic();out={'tool':name,'arguments':args,'started_epoch':time.time(),'returned':None,'error':None}
  try:
   if calls:raise ValueError('at most one execution')
   if name=='read_record':
    if args!={'record_id':'trial-A'}:raise ValueError('unknown record/arguments')
    result={'record_id':'trial-A','accuracy':'0.6786','status':'succeeded'}
   elif name=='compare_decimal':
    if set(args)!={'left','right'} or any(type(v)!=str for v in args.values()):raise ValueError('exact string arguments required')
    a,b=Decimal(args['left']),Decimal(args['right'])
    if not a.is_finite() or not b.is_finite():raise ValueError('finite only')
    result={'relation':'less' if a<b else 'greater' if a>b else 'equal','difference':str(a-b)}
   else:raise ValueError('unknown tool')
   out['returned']=result
  except Exception as e:out['error']=type(e).__name__+': '+str(e)
  finally:
   out['elapsed_seconds']=time.monotonic()-t;calls.append(out);save(case_dir/f'tool-{len(calls):02}.json',out)
  return json.dumps(out['returned'] if out['error'] is None else {'error':out['error']})
 s=test['schema'];transport=Transport(key,s)
 client=AsyncOpenAI(base_url=CONFIG['model_base_url'],api_key='local-unused',max_retries=0,timeout=120,http_client=httpx.AsyncClient(transport=transport,timeout=120,trust_env=False))
 executor=sdk.OpenAIAgentsSDKExecutor(client=client,use_responses=False,model=MODEL,retry_policy=RetryPolicy(max_retries=0,timeout_per_request_s=120));executor._tool_executor=dispatch
 payload=json.loads(json.dumps(test['frozen_payload']))
 assert payload['deterministic_audit']==test['audit_execution']['returned']
 save(case_dir/'deterministic-audit.json',test['audit_execution'])
 system=conf[arm]['system']
 try:
  async with asyncio.timeout(120):
   async for e in executor.run_turn([{'role':'user','content':json.dumps(payload),'session_id':'G14-'+key}],TOOLS if test['kind']=='tool' else [],system,ExecutorConfig(model=MODEL,max_tokens=2048,extra={'max_tokens':2048,'max_turns':1,'reasoning_effort':'none','parallel_tool_calls':False})):
    events.append({'type':type(e).__name__,'repr':repr(e)})
    if isinstance(e,TextChunk):text+=e.text
    if isinstance(e,ExecutorError):errors.append(e.message)
 except Exception as e:
  errors.append(type(e).__name__+': '+str(e))
  if isinstance(e,(TimeoutError,httpx.HTTPError)):transport.infrastructure_error=type(e).__name__
 finally:await executor.close();await client.close()
 (case_dir/'original.txt').write_text(text);save(case_dir/'sdk-events.json',events)
 score={'case':key,'test_id':test['id'],'arm':arm,'split':test['split'],'kind':test['kind'],'elapsed_seconds':time.monotonic()-start,'sent':transport.sent,'infrastructure_error':transport.infrastructure_error,'sdk_errors':errors,'tool_calls':calls,'original':text,'structure_valid':None,'objective_pass':False,'explanation_review':'pending reviewer B'}
 if test['kind']=='tool':
  ex=test['expected'];score['objective_pass']=len(calls)==1 and calls[0]['tool']==ex['tool'] and calls[0]['arguments']==ex['arguments'] and calls[0]['returned']==ex['return'] and calls[0]['error'] is None
  score['one_step_termination']='max-turn error after tool execution is retained, not counted as infrastructure failure; no follow-up comprehension claim'
 else:
  try:
   o=json.loads(text);score['parsed']=o
   score['structure_valid']=set(o)==set(s['required']) and isinstance(o['explanation'],str) and isinstance(o['answer'],str)
   expected=test['expected'];score['objective_pass']=score['structure_valid'] and o['answer']==expected['answer']
   if expected['value'] is None:score['objective_pass']=score['objective_pass'] and o['value'] is None
   else:score['objective_pass']=score['objective_pass'] and type(o['value']) in (float,int) and abs(Decimal(str(o['value']))-Decimal(str(expected['value'])))<=Decimal(str(conf['numeric_tolerance_pp']))
  except Exception as e:score['parse_error']=str(e);score['structure_valid']=False
 finish=[]
 if transport.sent and hasattr(transport,'response_file') and transport.response_file.exists():
  for line in transport.response_file.read_text().splitlines():
   if line.startswith('data: ') and line[6:]!='[DONE]':
    try:finish.extend(c.get('finish_reason') for c in json.loads(line[6:]).get('choices',[]) if c.get('finish_reason'))
    except Exception:pass
 score['finish_reasons']=finish;score['execution_complete']=transport.sent and not errors and not transport.infrastructure_error and finish==['stop']
 score['objective_pass']=bool(score['objective_pass'] and score['execution_complete'])
 save(case_dir/'score.json',score);print(json.dumps({k:score[k] for k in ['case','elapsed_seconds','objective_pass','infrastructure_error']},ensure_ascii=False),flush=True)
 return score
async def main():
 assert socket.gethostname()==CONFIG['remote_expected_hostname']
 assert hashlib.sha256((ROOT/'config.json').read_bytes()).hexdigest()==(ROOT/'FROZEN.sha256').read_text().strip()
 lock=(ROOT/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (ROOT/'cases').exists():raise RuntimeError('No replay of completed/ambiguous batch authorized')
 gate=load(ROOT/'execution-gate.json');assert gate['approved'] is True and gate['preflight_pass'] is True
 for rel,expected in gate['sha256'].items():
  target=ROOT.parent.parent/'qwen_batch.py' if rel=='qwen_batch.py' else ROOT/rel
  assert hashlib.sha256(target.read_bytes()).hexdigest()==expected, 'Gate hash mismatch '+rel
 conf=load(ROOT/'config.json');rows=[];prior=None;started=time.monotonic()
 for t in conf['tests']:
  for arm in ('baseline','selected'):
   if (ROOT.parent.parent/'STOP').exists():
    save(ROOT/'stop-reason.json',{'reason':'persistent stop marker'});save(ROOT/'evaluation.json',rows);return
   if time.monotonic()-started>=595:raise RuntimeError('batch wall clock limit')
   row=await case(t,arm,conf);rows.append(row)
   # Atomically preserve partial evaluation for cancellation/recovery.
   temp=ROOT/'evaluation.tmp';temp.write_text(json.dumps(rows,indent=2));os.replace(temp,ROOT/'evaluation.partial.json')
   err=row['infrastructure_error']
   if err and prior==err:
    save(ROOT/'stop-reason.json',{'reason':'two consecutive identical infrastructure errors','error':err});save(ROOT/'evaluation.json',rows);return
   prior=err
 save(ROOT/'evaluation.json',rows)
 save(ROOT/'completed.json',{'elapsed_seconds':time.monotonic()-started,'requests':len(rows),'status':'completed'})
if __name__=='__main__':asyncio.run(main())
