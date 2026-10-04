"""Offline scoring of public recorded outputs; never calls a model or network."""
import json
from decimal import Decimal
from pathlib import Path
root=Path(__file__).resolve().parent
fixtures=json.loads((root/'fixtures.json').read_text())['rounds']
outputs=json.loads((root/'outputs.json').read_text())['cases']
for round_data in fixtures:
    n=round_data['round']; tests={t['id']:t for t in round_data['tests']}
    for arm in ('baseline','selected'):
        passes=0
        for row in [r for r in outputs if r['round']==n and r['arm']==arm]:
            t=tests[row['test_id']]; expected=t['expected']
            if t['kind']=='tool':
                calls=row['tool_calls']; ok=len(calls)==1 and calls[0]['tool']=='compare_decimal' and calls[0]['arguments']=={'left':expected['left'],'right':expected['right']}
                if ok:
                    delta=Decimal(expected['left'])-Decimal(expected['right'])
                    relation='greater' if delta>0 else 'less' if delta<0 else 'equal'
                    ok=calls[0]['returned']=={'relation':relation,'difference':str(delta)}
            else:
                try:
                    p=json.loads(row['output']); ok=p['answer']==expected['answer']
                    if expected['value'] is None: ok=ok and p['value'] is None
                    else: ok=ok and abs(Decimal(str(p['value']))-Decimal(str(expected['value'])))<=Decimal(str(round_data['numeric_tolerance_pp']))
                except (ValueError,KeyError,TypeError): ok=False
            assert bool(ok)==row['objective_pass'], 'Recorded score mismatch'
            passes+=bool(ok)
        print(f'Round {n} {arm}: {passes}/6 objective checks')
print('Objective reproduction passed. Explanation review is independent human-readable evidence, not recomputed by this script.')
