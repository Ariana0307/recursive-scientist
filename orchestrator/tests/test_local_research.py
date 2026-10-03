"""Offline boundary tests only: no real generation, training, or claimed handoff."""
import asyncio
import json
import tempfile
from pathlib import Path
import unittest
import httpx
from pydantic import ValidationError
from orchestrator.local_research import GuardedTransport,Planner,Hypothesis,sample_proposal

class Boundaries(unittest.TestCase):
    def request(self, **changes):
        body={'model':'qwen3:4b','max_tokens':1000,'reasoning_effort':'none','messages':[]}
        body.update(changes)
        return httpx.Request('POST','http://127.0.0.1:11434/v1/chat/completions',json=body,
                            extensions={'timeout':dict(connect=120,read=120,write=120,pool=120)})

    def test_rejects_unsafe_before_network(self):
        async def check():
            with tempfile.TemporaryDirectory() as d:
                def never(request):self.fail('unsafe request reached transport')
                t=GuardedTransport(Path(d),httpx.MockTransport(never))
                for req in [self.request(max_tokens=1001),self.request(max_tokens=None),self.request(tools=[{'type':'function'}]),self.request(model='cloud'),self.request(reasoning_effort='high'),httpx.Request('POST','https://example.com',json={})]:
                    with self.assertRaises(ValueError):await t.handle_async_request(req)
                self.assertEqual(list(Path(d).glob('request-*.json')),[])
                await t.aclose()
        asyncio.run(check())

    def test_budget_persists_across_transport_instances(self):
        async def check():
            with tempfile.TemporaryDirectory() as d:
                def success(request):return httpx.Response(200,content=b'unit-test-response')
                t=GuardedTransport(Path(d),httpx.MockTransport(success))
                for _ in range(6):
                    r=await t.handle_async_request(self.request());await r.aread();await r.aclose()
                await t.aclose()
                t=GuardedTransport(Path(d),httpx.MockTransport(success))
                with self.assertRaisesRegex(ValueError,'budget exhausted'):await t.handle_async_request(self.request())
                self.assertEqual(len(list(Path(d).glob('request-*.json'))),6)
                await t.aclose()
        asyncio.run(check())

    def test_no_numeric_or_command_agent_fields(self):
        base={'role':'Planner','hypothesis_id':'H1','variable':'learning_rate','direction':'lower','action':'propose_only_no_dispatch'}
        for k,v in [('learning_rate',0.003),('command','echo'),('path','/tmp/x'),('epochs',4)]:
            with self.assertRaises(ValidationError):Planner.model_validate(dict(base,**{k:v}))
        with self.assertRaises(ValidationError):Planner.model_validate(dict(base,direction='enable'))

    def test_sampler_and_reference_binding(self):
        h=Hypothesis.model_validate({'role':'Hypothesis','candidates':[
          {'hypothesis_id':'H1','variable':'learning_rate','direction':'lower','prediction':'effect_uncertain'},
          {'hypothesis_id':'H2','variable':'augmentation','direction':'enable','prediction':'validation_accuracy_may_increase'}],
          'uncertainty':'untested_no_causal_evidence'})
        p=Planner.model_validate({'role':'Planner','hypothesis_id':'H1','variable':'learning_rate','direction':'lower','action':'propose_only_no_dispatch'})
        a=sample_proposal(p,h);self.assertEqual(a['parameters']['learning_rate'],.0003)
        self.assertEqual(a,sample_proposal(p,h));self.assertFalse(a['training_dispatched'])
        changed=p.model_copy(update={'hypothesis_id':'H2'})
        with self.assertRaises(ValueError):sample_proposal(changed,h)

if __name__=='__main__':unittest.main()
