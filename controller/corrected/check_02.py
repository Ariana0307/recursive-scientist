import json,sys,socket,hashlib
from pathlib import Path
from decimal import Decimal
r=Path(sys.argv[1]);c=json.loads((r/'config.json').read_text());checks=[]
for t in c['tests']:
 p=[json.loads((r/'payloads'/f'batch-1-{t["id"]}-{a}.json').read_text()) for a in ('baseline','selected')]
 for x in p:x['messages'][0]['content']='SYSTEM_PROMPT_ONLY_DIFFERENCE'
 assert p[0]==p[1]
 inp=t['input'];audit=t['frozen_payload']['deterministic_audit']
 if t['kind']=='numeric':
  d=(Decimal(inp['current'])-Decimal(inp['reference']))*100;ans='current' if d>0 else 'reference' if d<0 else 'tie';value=float(d)
  assert audit['winner']==ans and type(audit['delta_pp']) in (int,float) and Decimal(str(audit['delta_pp']))==d
 else:
  f=inp['facts'];ans='unknown' if 'p' not in f else 'reject' if Decimal(str(f['p']))<Decimal(str(f['alpha'])) else 'fail_to_reject';value=None
  assert audit['test_status']==ans
 assert t['expected']=={'answer':ans,'value':value}
 checks.append({'test_id':t['id'],'identical_pair':True,'independent_truth':{'answer':ans,'value':value}})
out={'hostname':socket.gethostname(),'role':'independent_protocol_and_objective_auditor','gpu_used':False,'qwen_requests':0,'checks':checks,'pass':True,'config_sha256':hashlib.sha256((r/'config.json').read_bytes()).hexdigest()}
if (r/'evaluation.json').exists():
 rows=[]
 for row in json.loads((r/'evaluation.json').read_text()):
  truth=next(x['independent_truth'] for x in checks if x['test_id']==row['test_id']);passed=False
  try:
   v=json.loads(row['original']);passed=set(v)=={'answer','value','explanation'} and isinstance(v['explanation'],str) and v['answer']==truth['answer'] and ((v['value'] is None) if truth['value'] is None else type(v['value']) in (int,float) and abs(Decimal(str(v['value']))-Decimal(str(truth['value'])))<=Decimal('1e-9'))
  except Exception:pass
  passed=bool(passed and row.get('execution_complete') is True and row.get('sent') is True and not row.get('sdk_errors') and not row.get('infrastructure_error'));rows.append({'case':row['case'],'test_id':row['test_id'],'arm':row['arm'],'objective_pass':passed,'agrees_with_01':passed==row['objective_pass']})
 out['results']=rows;out['all_agree']=all(x['agrees_with_01'] for x in rows)
print(json.dumps(out,indent=2))
