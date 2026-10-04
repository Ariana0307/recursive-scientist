"""No network, Codex calls, Qwen requests or remote process creation."""
import ast
import tempfile
from pathlib import Path
from audit_contract import build_pair
from lifecycle import Store
from runtime_config import require_execution
from ssh_adapter import rpc_argv

for source in Path(__file__).parent.rglob('*.py'):
    ast.parse(source.read_text(), filename=str(source))
for left, right, winner, delta in [('0.8','0.7','current',10.0), ('0.7','0.8','reference',-10.0), ('0.7','0.7','tie',0.0)]:
    a,b,execution=build_pair({'kind':'numeric','input':{'current':left,'reference':right}},'both')
    assert a == b and a['deterministic_audit'] == {'winner':winner,'delta_pp':delta,'units':'percentage_points'}
for facts,status in [({'statistical_test':'not performed'},'unknown'),({'p':0.05,'alpha':0.05},'fail_to_reject'),({'p':0.01,'alpha':0.05},'reject')]:
    a,b,_=build_pair({'kind':'evidence','input':{'facts':facts}},'both')
    assert a==b and a['deterministic_audit']['test_status']==status
with tempfile.TemporaryDirectory() as tmp:
    state=Store(tmp)
    assert state.reserve('batch-1') is True
    assert state.reserve('batch-1') is False
    state.request_stop('offline check')
    assert state.stopped()
    state.finalize('stopped',False,'remote confirmation not tested')
    assert state.read('state.json')['status']=='stopping'
assert 'ForwardAgent=no' in rpc_argv('status','batch-1')
try:
    require_execution()
except RuntimeError:
    pass
else:
    raise AssertionError('example config must disable execution')
print('PASS: syntax; six shared audit fixtures; durable reservation and stop-pending state; SSH argv; disabled execution')
