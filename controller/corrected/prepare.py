import json,hashlib,asyncio,os,sys,shutil
from pathlib import Path
from audit_contract import build_pair
C=Path(__file__).resolve().parent;R=C.parent
p=json.loads((C/'frozen-proposal.json').read_text());assert len(p['tests'])==6
old=json.loads((C/'historical-reference.json').read_text())
for arm in ('baseline','selected'):
 s=p[arm].get('system',p[arm].get('system_prompt'));assert s==old[arm]['system'];p[arm]['system']=s
schema=old['tests'][0]['schema'];p['numeric_tolerance_pp']=1e-9
for t in p['tests']:
 t['schema']=schema;t['split']='g14-fresh-confirmation'
 a,b,ex=build_pair(t,'both')
 # Preserve complete researcher-authored shared task including explicit evidence limits.
 a['task']=t['input']['task'];b['task']=t['input']['task'];assert a==b
 t['frozen_payload']=a;t['audit_execution']=ex
(C/'config.json').write_text(json.dumps(p,indent=2));sha=hashlib.sha256((C/'config.json').read_bytes()).hexdigest();(C/'FROZEN.sha256').write_text(sha)
dry=R/'offline-capture/runs/batch-1';dry.mkdir(parents=True);shutil.copy(C/'config.json',dry/'config.json');shutil.copy(C/'FROZEN.sha256',dry/'FROZEN.sha256')
sys.argv=['qwen_batch.py',str(dry)];os.environ['G14_CAPTURE_ONLY']='1'
import qwen_batch
async def go():
 for t in p['tests']:
  for arm in ('baseline','selected'):await qwen_batch.case(t,arm,p)
asyncio.run(go())
shutil.copytree(dry/'payloads',C/'payloads')
assert len(list((C/'payloads').glob('*.json')))==12
assert len(list((R/'offline-capture/ledger').glob('request-*.json')))==0
(C/'dispatcher-check.json').write_text(json.dumps({'method':'Actual installed Omnigent SDK constructs payload; Transport intercepts before any HTTP, records exact outbound JSON; live Transport must equal each preview before reserve/send','captured_payloads':12,'offline_http_requests':0,'same_shared_input_per_pair':True,'audit_computed_once_per_test':True,'config_sha256':sha},indent=2))
