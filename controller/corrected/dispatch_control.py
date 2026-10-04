import json,subprocess,time,hashlib,shutil,socket,sys
from runtime_config import CONFIG, require_execution, ssh_args
import shlex
from pathlib import Path
C=Path(__file__).resolve().parent;R=C.parent
SSH=ssh_args();SCP=ssh_args(copy=True);H1=CONFIG['ssh_host'];H2=CONFIG['scorer_ssh_host'];REMOTE=CONFIG['remote_root']
def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=60)
 if p.returncode:raise RuntimeError(p.stderr)
 return p.stdout
def save(name,obj):(C/name).write_text(json.dumps(obj,indent=2))
def copy02(evaluation=False):
 cmd(SSH+[H2,f'mkdir -p {REMOTE}/audit'])
 files=['config.json','check_02.py']+(['evaluation.json'] if evaluation else [])
 cmd(SCP+['-r']+[str(C/x) for x in files]+[str(C/'payloads'),H2+':'+REMOTE+'/audit/'])
 out=json.loads(cmd(SSH+[H2,f'{shlex.quote(CONFIG["remote_python"])} {REMOTE}/audit/check_02.py {REMOTE}/audit']))
 save('score-02.json' if evaluation else 'preflight-02.json',out);assert out['pass']
require_execution()
mode=sys.argv[1]
if mode=='precheck':
 copy02();save('pre-review-ready.json',{'ready':True});sys.exit()
review=json.loads((C/'pre-review.json').read_text());preflight=json.loads((C/'preflight-02.json').read_text());candidate=json.loads((C/'gate-candidate.json').read_text())
assert review['approved'] is True and preflight['pass'] is True
assert preflight['config_sha256']==hashlib.sha256((C/'config.json').read_bytes()).hexdigest()
assert review['reviewed_sha256']==candidate['sha256']
for rel,digest in candidate['sha256'].items():assert hashlib.sha256((C/rel).read_bytes()).hexdigest()==digest
assert not (C/'dispatch-reserved.json').exists(),'Do not repeat ambiguous dispatch'
save('dispatch-reserved.json',{'hostname':socket.gethostname(),'trigger':'5060 controller after real Codex pre-review approval','epoch':time.time(),'budget':12})
cmd(SSH+[H1,f'mkdir -p {REMOTE}/runs/batch-1'])
cmd(SCP+[str(C/'qwen_batch.py'),str(C/'remote_job.py'),str(C/'runtime_config.py'),str(C/'runtime.json'),H1+':'+REMOTE+'/'])
gate={'approved':review['approved'],'preflight_pass':preflight['pass'],'sha256':{str(f.relative_to(C)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [C/'config.json',C/'qwen_batch.py',*sorted((C/'payloads').glob('*.json'))]}}
assert gate['sha256']==json.loads((C/'gate-candidate.json').read_text())['sha256']
save('execution-gate.json',gate)
cmd(SCP+['-r',str(C/'config.json'),str(C/'FROZEN.sha256'),str(C/'execution-gate.json'),str(C/'payloads'),H1+':'+REMOTE+'/runs/batch-1/'])
s=json.loads(cmd(SSH+[H1,f'{shlex.quote(CONFIG["remote_python"])} {REMOTE}/remote_job.py start batch-1']));save('execution-start.json',s)
while s['running']:
 time.sleep(2);s=json.loads(cmd(SSH+[H1,f'{shlex.quote(CONFIG["remote_python"])} {REMOTE}/remote_job.py status batch-1']));save('execution-status.json',s)
target=R/'evidence/remote';target.mkdir(parents=True,exist_ok=True)
cmd(SCP+['-r',H1+':'+REMOTE+'/runs',H1+':'+REMOTE+'/ledger',str(target)])
for name in ['show.json','tags.json','version.json','service.json']:cmd(SCP+[H1+':'+REMOTE+'/'+name,str(target)])
save('execution-finish.json',s)
b=target/'runs/batch-1';ep=b/'evaluation.json' if (b/'evaluation.json').exists() else b/'evaluation.partial.json';shutil.copy(ep,C/'evaluation.json')
reqs=list((target/'ledger').glob('request-*.json'));assert len(reqs)<=12
for f in reqs:
 r=json.loads(f.read_text());assert r['payload']==json.loads((C/'payloads'/(r['case']+'.json')).read_text())
save('execution-fidelity.json',{'actual_requests':len(reqs),'historical_requests':24,'separate_budget':12,'all_sent_payloads_equal_frozen':True,'complete':s['completed'],'remote_exited':not s['running'],'forced_cancel_tested':False,'same_audits':True})
copy02(True);save('post-review-ready.json',{'ready':True})
print('EXECUTION_AND_02_COMPLETE',flush=True)
