raise RuntimeError("Historical source archive only: unequal audit protocol; do not execute. Use a separately reviewed corrected dispatcher.")
"""Independent stdlib/Decimal score reproduction on 02. No model/GPU execution."""
import json,sys,socket,hashlib,datetime
from decimal import Decimal
from pathlib import Path
root=Path(sys.argv[1]);reports=[]
for batch in sorted((root/'runs').glob('batch-*')):
 conf=json.loads((batch/'config.json').read_text());raw=json.loads((batch/'evaluation.json').read_text());out=[]
 assert hashlib.sha256((batch/'config.json').read_bytes()).hexdigest()==(batch/'FROZEN.sha256').read_text().strip()
 for row in raw:
  test=next(x for x in conf['tests'] if x['id']==row['test_id']);data=test['input'];kind=test['kind']
  if kind=='numeric':
   a,b=Decimal(data['current']),Decimal(data['reference']);truth={'answer':'current' if a>b else 'reference' if a<b else 'tie','value':(a-b)*100}
   p=json.loads(row['original']);passed=p['answer']==truth['answer'] and abs(Decimal(str(p['value']))-truth['value'])<=Decimal(str(conf['numeric_tolerance_pp']))
  elif kind=='evidence':
   f=data.get('facts',{});truth={'answer':('reject' if Decimal(str(f['p']))<Decimal(str(f['alpha'])) else 'fail_to_reject') if 'p' in f else 'unknown'}
   p=json.loads(row['original']);passed=p['answer']==truth['answer'] and p['value'] is None
  else:
   calls=row['tool_calls'];ex=test['expected'];args=ex['arguments'];a,b=Decimal(args['left']),Decimal(args['right']);truth={'relation':'less' if a<b else 'greater' if a>b else 'equal','difference':str(a-b)}
   passed=len(calls)==1 and calls[0]['arguments']==args and calls[0]['tool']=='compare_decimal' and calls[0]['returned']==truth and calls[0]['error'] is None
  out.append({'case':row['case'],'independent_truth':{k:str(v) if isinstance(v,Decimal) else v for k,v in truth.items()},'reproduced_pass':passed,'agrees_with_01':passed==row['objective_pass']})
 reports.append({'batch':batch.name,'results':out})
print(json.dumps({'hostname':socket.gethostname(),'task':'independent Decimal score reproduction','gpu_used':False,'qwen_requests':0,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reports':reports,'all_agree':all(x['agrees_with_01'] for b in reports for x in b['results'])},indent=2))
