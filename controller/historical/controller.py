raise RuntimeError("Historical source archive only: unequal audit protocol; do not execute. Use a separately reviewed corrected dispatcher.")
"""Bounded G11: Omnigent Codex decisions -> SSH experiments -> independent review."""
import asyncio,json,time,hashlib,datetime,subprocess,os,sys,fcntl
from pathlib import Path
from decimal import Decimal
from lifecycle import Store,Stopped
from prepare_batch import freeze,SCHEMA,make_test
from omnigent_team import OmnigentTeam
ROOT=Path(__file__).resolve().parents[1];S=Store(ROOT/'control');HOST='configured-model-worker';REMOTE='/srv/research/historical-run'
SSH=['ssh','-i','/configured/private/ssh-identity','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','StrictHostKeyChecking=yes','-o','ForwardAgent=no']
SCP=['scp','-q','-i','/configured/private/ssh-identity','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes']
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,ensure_ascii=False))
def cmd(argv,timeout=30):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError('Command failed: '+p.stderr[-1200:])
 return p.stdout
def rpc(action,batch):return json.loads(cmd(SSH+[HOST,f'python3 {REMOTE}/remote_job.py {action} {batch}']))
def state(**kw):
 x=S.read('state.json');x.update(kw,updated_at=now());S.write('state.json',x)
def event(phase,text,**kw):S.event(phase,text,**kw)
def parse(result):
 text=result['text'].strip()
 if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0]
 return json.loads(text)
def check_stop():
 if S.stopped():raise Stopped('persistent stop intent')
async def turn(team,role,prompt,upstream=None):
 check_stop();state(phase=role+' reviewing evidence',status='running')
 # Global role turn cap: first choice, review1, next decision, review2, plus ONE correction.
 counters=S.read('agent-turns.json',{'count':0})
 if counters['count']>=8:raise RuntimeError('Codex attempt cap (4 research + 1 correction + 3 recorded pre-inference interface failures)')
 counters['count']+=1;S.write('agent-turns.json',counters)
 event('agent_call','Omnigent submits bounded '+role+' turn',agent=role,session='pending',evidence_path='evidence/omnigent/events.jsonl',type='handoff',upstream=upstream)
 result=await team.turn(role,prompt,upstream=upstream)
 x=S.read('state.json');agents=x['agents']
 for a in agents:
  if a['id']==role:a.update(session_id=result.get('conversation_id',result.get('response_id','unknown')),status='completed turn',task='Evidence-grounded '+role+' turn returned',model=result.get('model','unknown'))
 state(agents=agents)
 event('agent_result',role+' returned a real Omnigent Codex response',agent=role,session=result.get('response_id','unknown'),evidence_path='evidence/omnigent/'+result['call_id']+'.result.json',type='handoff_return')
 return result
async def execute(batch):
 check_stop();p=ROOT/'control'/'batches'/batch
 if not S.reserve(batch):
  prior=S.read('jobs/'+batch+'.json')
  if prior['status']=='completed':return json.loads((ROOT/'evidence/remote/runs'/batch/'evaluation.json').read_text())
  raise RuntimeError('Unconfirmed dispatch checkpoint; reconcile status, do not repeat')
 cmd(SSH+[HOST,f'mkdir -p {REMOTE}/runs/{batch}'])
 cmd(SCP+[str(p/'config.json'),str(p/'FROZEN.sha256'),HOST+f':{REMOTE}/runs/{batch}/'])
 check_stop();started=time.monotonic();status=rpc('start',batch)
 save(ROOT/'evidence'/f'{batch}-start.json',status)
 state(status='running',phase='Executing Qwen experiment',round_id=batch,stop={'requested':False,'remote_confirmed':False,'detail':'Owned bounded remote job running.'})
 event('execute','Frozen batch dispatched to local Qwen on 5090-01',round_id=batch,experiment_id=batch,evidence_path=f'control/batches/{batch}/config.json',type='experiment_started')
 while status['running']:
  if S.stopped():
   state(status='stopping',phase='Awaiting remote stop confirmation')
   try:status=rpc('stop',batch)
   except Exception as e:
    save(ROOT/'evidence/stop-pending.json',{'error':str(e),'remote_confirmed':False});raise Stopped('SSH unavailable: stop intent persists; remote bounded job unconfirmed')
   save(ROOT/'evidence/remote-stop.json',status);raise Stopped('owned remote stop '+('confirmed' if not status['running'] else 'pending'))
  await asyncio.sleep(.7)
  status=rpc('status',batch)
  x=S.read('state.json');u=x['usage'];u['qwen_requests']=status['requests'];state(usage=u)
  if time.monotonic()-started>610:raise RuntimeError('remote wall limit exceeded; investigate')
 elapsed=time.monotonic()-started
 target=ROOT/'evidence/remote';target.mkdir(exist_ok=True)
 # SCP overlays small immutable per-batch outputs and append-only ledger, never remote old G10.
 cmd(SCP+['-r',HOST+':'+REMOTE+'/runs',str(target)],timeout=60)
 cmd(SCP+['-r',HOST+':'+REMOTE+'/ledger',str(target)],timeout=60)
 for name in ('show.json','tags.json','version.json','service.json'):
  cmd(SCP+[HOST+':'+REMOTE+'/'+name,str(target)])
 save(ROOT/'evidence'/f'{batch}-finish.json',status)
 if not status['completed']:raise RuntimeError('Remote job terminated without completed checkpoint; partial outputs retained')
 rows=json.loads((target/'runs'/batch/'evaluation.json').read_text())
 S.finish(batch,{'requests':len(rows),'elapsed_seconds':elapsed,'evidence_path':f'evidence/remote/runs/{batch}/evaluation.json'})
 total=sum(S.read('jobs/'+b+'.json',{}).get('result',{}).get('elapsed_seconds',0) for b in ('batch-1','batch-2'))
 x=S.read('state.json');u=x['usage'];u.update(qwen_requests=status['requests'],experiment_seconds=total);state(usage=u,phase='Results arrived; independent review queued',stop={'requested':False,'remote_confirmed':True,'detail':'Remote batch process confirmed exited.'})
 event('result','Real Qwen results arrived and trigger independent Codex review',round_id=batch,experiment_id=batch,evidence_path=f'evidence/remote/runs/{batch}/evaluation.json',type='experiment_completed',requests=len(rows))
 return rows
async def review(team,batch,rows):
 slim=[{k:x.get(k) for k in ('case','arm','kind','objective_pass','original','tool_calls','infrastructure_error','sdk_errors')} for x in rows]
 path=ROOT/'control'/f'{batch}-review-input.json';save(path,slim)
 prompt=f'''Independently review the actual Qwen originals in {path}. You MUST call read_evidence on this path. These are synthetic tests, not empirical p-values about Qwen. Read {ROOT}/control/batches/{batch}/config.json for frozen questions/answers. Do not use keywords alone. Evaluate complete explanations: unknown is not non-significance; failing to reject is not equivalence/no effect; provided p below alpha does reject the supplied null but not establish causality or practical importance. Numeric tolerance is 1e-9 percentage points. Tools have no requested prose: scientific_pass=true if no invented content, program handles execution. Preserve offending quote and reason. Output ONLY JSON {{"per_case":[{{"case":"exact case id","scientific_pass":true,"reason":"reason","quote":"quote or empty"}}],"conclusion":"brief","next_test_suggestion":"evidence-based"}} with exactly one row per input case. Don't run experiments, spawn agents or ask user approval. No unsupported superiority claims.'''
 result=await turn(team,'reviewer',prompt,{'batch':batch,'evidence':str(path)})
 parsed=parse(result)
 if {x['case'] for x in parsed.get('per_case',[])}!={x['case'] for x in rows}:raise ValueError('review lacks complete case coverage')
 save(ROOT/'control'/f'{batch}-review.json',parsed)
 by={x['case']:x for x in parsed['per_case']};scored=[]
 for arm in ('baseline','selected'):
  rr=[x for x in rows if x['arm']==arm];objective=sum(bool(x['objective_pass']) for x in rr)
  scientific=sum(by[x['case']]['scientific_pass'] is True for x in rr)
  scored.append({'name':arm,'score':objective,'out_of':len(rr),'scientific_pass':scientific,'accepted':objective==len(rr) and scientific==len(rr),'metric_version':'g11-v1/'+batch,'evidence_path':f'control/{batch}-review.json','scope':'only frozen synthetic fixture cohort'})
 # Ties prefer the existing reference, avoiding gratuitous replacement.
 observed=max(scored,key=lambda x:x['score']);accepted=next((x for x in scored if x['accepted']),None)
 prev=S.read('best.json',{});history=prev.get('cohorts',[])+[{'batch':batch,'scored':scored,'best_observed':observed,'best_accepted':accepted}]
 best={'best_observed':observed,'best_accepted':accepted,'cohorts':history,'previous_accepted_preserved':[h['best_accepted'] for h in history[:-1] if h['best_accepted']],'updated_at':now()}
 S.write('best.json',best);S.write('best-'+batch+'.json',best)
 state(best_observed=observed,best_accepted=accepted,learned=[parsed['conclusion']])
 event('review',parsed['conclusion'],agent='reviewer',session=result['response_id'],round_id=batch,experiment_id=batch,evidence_path=f'control/{batch}-review.json',type='review_completed')
 event('retain' if accepted else 'reject','Accepted only within frozen fixture scope' if accepted else 'No configuration meets all acceptance gates; no accepted best in this cohort',round_id=batch,evidence_path='control/best.json',type='best_updated')
 return parsed,result

def freeze_second(decision,first):
 action=decision['action'];assert action in ('confirm','pivot_fact_ledger')
 pairs=decision['numeric_pairs'];ev=decision['evidence_cases'];tool=decision['tool_pair']
 assert len(pairs)==2 and len(ev)==3 and len({x['state'] for x in ev})==3
 tests=[]
 for i,x in enumerate(pairs):
  a,b=Decimal(x['current']),Decimal(x['reference']);assert a.is_finite() and b.is_finite() and 0<=a<=1 and 0<=b<=1
  tests.append(make_test('N'+str(i+1),'numeric',{'task':'Compare accuracy fractions current minus reference in percentage points. answer=current/reference/tie; value=delta_pp; explain limits.','current':str(a),'reference':str(b),'evidence':'Fresh single-run synthetic comparison; no test supplied.'},{'answer':'current' if a>b else 'reference' if a<b else 'tie','value':float((a-b)*100)},'fresh-confirmation'))
 for i,x in enumerate(ev):
  status=x['state'];assert status in ('unknown','reject','fail_to_reject')
  facts={'design':'observational, no randomized intervention','equivalence_test':False}
  if status=='unknown':facts['statistical_test']='not performed'
  else:
   p,a=Decimal(str(x['p'])),Decimal(str(x['alpha']));assert 0<=p<=1 and 0<a<1
   assert ('reject' if p<a else 'fail_to_reject')==status
   facts.update(p=float(p),alpha=float(a),valid_test=True,pre_specified=True,null='zero mean paired difference')
  tests.append(make_test('E'+str(i+1),'evidence',{'task':'Classify supplied statistical evidence unknown/reject/fail_to_reject; value=null; explain limits without inventing evidence.','facts':facts},{'answer':status,'value':None},'fresh-confirmation'))
 a,b=Decimal(tool['left']),Decimal(tool['right']);assert a.is_finite() and b.is_finite()
 tests.append(make_test('T1','tool',{'task':f'Call compare_decimal exactly once with left="{tool["left"]}", right="{tool["right"]}" as exact decimal strings. Native call only.'},{'tool':'compare_decimal','arguments':tool,'return':{'relation':'less' if a<b else 'greater' if a>b else 'equal','difference':str(a-b)}},'fresh-confirmation'))
 for t in tests:t['split']='fresh-confirmation'
 conf=json.loads(json.dumps(first));conf.update(batch_id='batch-2',dataset_version='fresh-fixture-v2',tests=tests,freeze_utc=now(),decision_source='control/next-decision.json',intervention_scope='system_assisted' if action=='pivot_fact_ledger' else 'prompt_only')
 conf['baseline']=first['selected'];conf['selected']={'name':'result-driven '+action,'system':decision['next_prompt']}
 if action=='pivot_fact_ledger':
  # Actual deterministic audit is executed before model dispatch. Candidate-only evidence changes scope to system-assisted.
  for t in tests:
   if t['kind']!='tool':t['selected_audit']={'verified_expected':t['expected'],'source':'Decimal arithmetic / supplied p-alpha comparison; no inferred significance'}
 p=ROOT/'control/batches/batch-2';p.mkdir(parents=True,exist_ok=False);save(p/'config.json',conf);(p/'FROZEN.sha256').write_text(hashlib.sha256((p/'config.json').read_bytes()).hexdigest());return conf
async def main():
 run_lock=(ROOT/'control/controller.lock').open('a');fcntl.flock(run_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if (ROOT/'control/loop-completed.json').exists():print('Completed checkpoint retained; no work resubmitted');return
 if (ROOT/'control/first-decision.json').exists():raise RuntimeError('Existing scientific checkpoint: reconcile recorded result/review, never blindly restart pipeline')
 check_stop();first_choice=None
 try:
  async with OmnigentTeam() as team:
   state(orchestration={'status':'connected','detail':'Omnigent public CodexExecutor team ready; verifying actual Codex tool turn.','evidence_path':'evidence/omnigent/events.jsonl'})
   prompt=f'''You are experimental researcher. Read {ROOT}/control/candidate-spec.json and {ROOT}/handoffs/review_design.md via read_evidence, plus G10 REPORT.md if needed. Investigate the G10 failure distinction: 1e-16 representation error vs unsupported not statistically significant. Compare both proposed candidates; autonomously choose the most informative first batch within 12 Qwen calls, reserving 12. Output ONLY JSON {{"candidate_id":"C1 or C2","hypotheses":["hypothesis1","hypothesis2"],"reason":"evidence-grounded choice","limitations":["..."]}}. Do not run experiments or create agents. You can decide within these bounds without user approval.'''
   r=await turn(team,'researcher',prompt,{'prior_run':'G10','design':'control/candidate-spec.json'});choice=parse(r);assert choice['candidate_id'] in ('C1','C2');save(ROOT/'control/first-decision.json',choice)
   state(orchestration={'status':'verified_codex_turn','detail':'Omnigent registered researcher called Codex with real evidence tools; independent reviewer pending.','evidence_path':'evidence/omnigent/'+r['call_id']+'.result.json'},next_action={'kind':'execute_first_batch','reason':choice['reason'],'evidence_path':'control/first-decision.json'})
   event('candidate_selection',choice['reason'],agent='researcher',session=r['response_id'],evidence_path='control/first-decision.json',type='decision')
   first=freeze(ROOT/'control/batches/batch-1',choice['candidate_id'])
   rows=await execute('batch-1');review1,review_result=await review(team,'batch-1',rows)
   p=f'''The real first batch has completed and independent review is available. Read {ROOT}/control/batch-1-review.json and {ROOT}/control/best.json, plus originals at {ROOT}/control/batch-1-review-input.json via read_evidence. Reconsider your initial hypothesis and selection. Remaining budget <=12 Qwen calls and one new batch. Choose stop if no useful experiment remains. Otherwise choose confirm (fresh challenge/confirmation) or pivot_fact_ledger (candidate supplied actual deterministic facts, system-assisted scope). Do not blindly repeat a failed intervention. Output ONLY JSON {{"action":"confirm or pivot_fact_ledger or stop","reason":"specific result-driven reason","trigger_evidence":["case IDs/quotes"],"abandoned_hypothesis":"none or actual abandoned hypothesis","new_hypothesis":"...","next_prompt":"full selected system prompt; do not embed answers","numeric_pairs":[{{"current":"fraction","reference":"fraction"}},{{"current":"fraction","reference":"fraction"}}],"evidence_cases":[{{"state":"unknown"}},{{"state":"reject","p":0.0,"alpha":0.0}},{{"state":"fail_to_reject","p":0.0,"alpha":0.0}}],"tool_pair":{{"left":"decimal string","right":"decimal string"}}}}. Use NEW numerical/p-values never used in batch1; valid p/alpha; no actual significance claims about this tiny model comparison. For stop omit fixture fields. This is actual autonomous selection: experiment two will be derived from your decision, not predetermined.'''
   rr=await turn(team,'researcher',p,{'review_response_id':review_result['response_id'],'batch':'batch-1'});decision=parse(rr);save(ROOT/'control/next-decision.json',decision)
   state(next_action={'kind':decision['action'],'reason':decision['reason'],'evidence_path':'control/next-decision.json'})
   event('pivot' if decision['action']=='pivot_fact_ledger' else 'next_decision',decision['reason'],agent='researcher',session=rr['response_id'],round_id='batch-1',evidence_path='control/next-decision.json',type='decision_changed')
   if decision['action']=='stop':
    state(status='completed',phase='Evidence-based bounded stop');event('complete','Researcher chose stop; second automatic experiment not demonstrated',evidence_path='control/next-decision.json')
   else:
    freeze_second(decision,first);rows2=await execute('batch-2');await review(team,'batch-2',rows2)
    state(status='completed',phase='Bounded two-batch loop completed',next_action={'kind':'proposal_only','reason':'Two-batch/24-request boundary reached. Preserve evidence and accepted best; no further dispatch.','evidence_path':'control/best.json'})
   state(orchestration={'status':'verified','detail':'Omnigent public CodexExecutor coordinated researcher and independent reviewer with persistent Codex threads, evidence tools and result-driven follow-up. Server session runner route remains unimplemented.','evidence_path':'evidence/omnigent/events.jsonl'})
   save(ROOT/'control/loop-completed.json',{'completed_at':now(),'status':S.read('state.json')['status']})
 except BaseException as e:
  save(ROOT/'control/loop-error.json',{'error_type':type(e).__name__,'error':str(e),'timestamp':now()})
  if not S.read('best.json'):S.save_best(None,None,'g11-v1')
  confirmed=False
  try:
   if S.stopped():rpc('stop','batch-1')
   confirmed=not any(rpc('status',b)['running'] for b in ('batch-1','batch-2'))
  except Exception:pass
  S.finalize('stopped' if S.stopped() else 'blocked',confirmed,str(e))
  event('stop' if S.stopped() else 'blocked',str(e),evidence_path='control/loop-error.json',type='terminal')
  raise
if __name__=='__main__':asyncio.run(main())
