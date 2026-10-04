"""Offline-validated future contract. NOT used in the exhausted G11 model run."""
from copy import deepcopy
from decimal import Decimal
import time

def build_audit(test):
 start=time.monotonic();p=test['input'];kind=test['kind']
 if kind=='numeric':
  a,b=Decimal(p['current']),Decimal(p['reference']);delta=(a-b)*100
  returned={'winner':'current' if delta>0 else 'reference' if delta<0 else 'tie','delta_pp':float(delta),'units':'percentage_points'}
 elif kind=='evidence':
  f=p.get('facts',{});status='unknown' if 'p' not in f else 'reject' if Decimal(str(f['p']))<Decimal(str(f['alpha'])) else 'fail_to_reject'
  returned={'test_status':status,'causality':'not_established','equivalence':'not_established'}
 else:return None
 return {'tool':'deterministic_evidence_audit','input':p,'returned':returned,'elapsed_seconds':time.monotonic()-start,'error':None}

def build_pair(test,audit_policy):
 if audit_policy not in ('both','none'):raise ValueError('This controlled prompt comparison requires explicitly declared equal audit policy')
 a,b=deepcopy(test['input']),deepcopy(test['input']);execution=None
 if audit_policy=='both' and test['kind']!='tool':
  execution=build_audit(test);a['deterministic_audit']=execution['returned'];b['deterministic_audit']=deepcopy(execution['returned'])
 if test['kind']=='numeric':
  for payload in (a,b):payload['task']='Return answer identifying HIGHER observed accuracy: current if current>reference, reference if current<reference, tie if equal. value is (current-reference)*100 in percentage points. Explain evidence limits.'
 assert a==b, 'Only system prompt may differ in this experiment'
 return a,b,execution
