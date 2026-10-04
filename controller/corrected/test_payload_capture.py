"""Exercise actual Omnigent SDK request construction; intercept before HTTP."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
os.environ['G14_CAPTURE_ONLY'] = '1'
os.environ['RS_CONFIG'] = str(HERE / 'runtime.json')

with tempfile.TemporaryDirectory() as tmp:
    run = Path(tmp) / 'runs' / 'batch-1'
    run.mkdir(parents=True)
    sys.argv = ['qwen_batch.py', str(run)]
    import qwen_batch
    protocol = json.loads((HERE / 'recorded-config.json').read_text())

    async def capture():
        for test in protocol['tests']:
            for arm in ('baseline', 'selected'):
                row = await qwen_batch.case(test, arm, protocol)
                assert row['sent'] is False

    asyncio.run(capture())
    payloads = list((run / 'payloads').glob('*.json'))
    assert len(payloads) == 12
    assert not list((Path(tmp) / 'ledger').glob('request-*.json'))
    for test in protocol['tests']:
        pair = []
        for arm in ('baseline', 'selected'):
            name = f'batch-1-{test["id"]}-{arm}.json'
            actual = json.loads((run / 'payloads' / name).read_text())
            recorded = json.loads((HERE / 'recorded-payloads' / name).read_text())
            assert actual == recorded, name
            user = json.loads(actual['messages'][1]['content'])
            assert user['deterministic_audit'] == test['audit_execution']['returned']
            actual['messages'][0]['content'] = 'ONLY_SYSTEM_PROMPT_DIFFERS'
            pair.append(actual)
        assert pair[0] == pair[1]
print('PASS: 12 actual SDK payloads equal recorded previews; six pairs identical except system prompt; exact shared audit; zero HTTP reservations')
