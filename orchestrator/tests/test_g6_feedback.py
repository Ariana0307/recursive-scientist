"""Offline G6 transport/context/SDK regressions. No real requests."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from orchestrator.local_research import GuardedTransport,Hypothesis,Planner,sample_proposal
from orchestrator.research_feedback import run_feedback,mock_transport,sampling_context,expected_comparison,LiveHypothesis
from orchestrator.research_tools import ResearchCapabilities,stable_bytes,sha
from orchestrator.tests.test_research_tools import synthetic_snapshot
from orchestrator.tests import test_local_research as transport_tests

class G6Feedback(unittest.TestCase):
    def test_live_mock_and_baseline_only_rejected(self):
        async def check(root):
            b=stable_bytes(synthetic_snapshot())
            with self.assertRaisesRegex(ValueError,'actual post-experiment'):ResearchCapabilities(b,sha(b),root,mode='live')
            b=stable_bytes(synthetic_snapshot(2));c=ResearchCapabilities(b,sha(b),root,mode='live')
            with self.assertRaisesRegex(ValueError,'mock forbidden'):await run_feedback(c,root,mock_transport(c),mode='live')
            c=ResearchCapabilities(b,sha(b),root,mode='cpu_mock')
            with self.assertRaises(ValueError):await run_feedback(c,root,object(),mode='cpu_mock')
        with tempfile.TemporaryDirectory() as d:asyncio.run(check(Path(d)))

    def test_eight_including_failures_and_restart(self):
        async def check(root):
            count=0
            def fail(req):
                nonlocal count
                count+=1;raise httpx.ConnectError('synthetic offline failure')
            for i in range(8):
                t=GuardedTransport(root,httpx.MockTransport(fail),max_requests=8)
                with self.assertRaises(httpx.ConnectError):await t.handle_async_request(transport_tests.Boundaries().request())
                await t.aclose()
            t=GuardedTransport(root,httpx.MockTransport(fail),max_requests=8)
            with self.assertRaisesRegex(ValueError,'budget exhausted'):await t.handle_async_request(transport_tests.Boundaries().request())
            self.assertEqual(count,8);self.assertEqual(len(list(root.glob('error-*.json'))),8)
            await t.aclose()
        with tempfile.TemporaryDirectory() as d:asyncio.run(check(Path(d)))

    def test_sampler_uses_last_completed_configuration(self):
        history=synthetic_snapshot(2);history['records'][-1]['parameters']={'learning_rate':.003,'weight_decay':.001,'augmentation':'basic'}
        context=sampling_context(history)
        h=Hypothesis.model_validate({'role':'Hypothesis','candidates':[{'hypothesis_id':'H1','variable':'learning_rate','direction':'higher','prediction':'effect_uncertain'},{'hypothesis_id':'H2','variable':'augmentation','direction':'disable','prediction':'effect_uncertain'}],'uncertainty':'untested_no_causal_evidence'})
        p=Planner(role='Planner',hypothesis_id='H1',variable='learning_rate',direction='higher',action='propose_only_no_dispatch')
        sample=sample_proposal(p,h,context_parameters=context['parameters'])
        self.assertEqual(sample['parameters']['weight_decay'],.001)
        self.assertEqual(sample['parameters']['learning_rate'],.003)
        self.assertFalse(sample['direction_has_alternative'])
        self.assertEqual(sample['parameters']['augmentation'],'basic')
        p=Planner(role='Planner',hypothesis_id='H2',variable='augmentation',direction='disable',action='propose_only_no_dispatch')
        self.assertEqual(sample_proposal(p,h,context_parameters=context['parameters'])['parameters']['augmentation'],'none')

    def test_sdk_round2_carries_actual_context_through_roles(self):
        async def check(root):
            obj=synthetic_snapshot(2);obj['records'][-1].update(parameters={'learning_rate':.003,'weight_decay':.001,'augmentation':'basic'},accuracy=.9)
            b=stable_bytes(obj);cap=ResearchCapabilities(b,sha(b),root/'proposals',mode='cpu_mock')
            result=await run_feedback(cap,root,mock_transport(cap),mode='cpu_mock')
            self.assertEqual(result['mock_transport_requests'],5);self.assertEqual(result['real_model_generations'],0)
            for role in ('Evaluator','Hypothesis','Planner'):
                inp=json.loads((root/f'{role}-input.json').read_text())
                self.assertEqual(inp['sampling_context']['parameters'],obj['records'][-1]['parameters'])
                self.assertEqual(inp['verified_history'],obj)
            self.assertEqual(cap.receipt['parameters'],obj['records'][-1]['parameters'])
            self.assertEqual(cap.receipt['round'],2)
            self.assertTrue((root/'sampling-H1.json').exists())
        with tempfile.TemporaryDirectory() as d:asyncio.run(check(Path(d)))

    def test_live_failure_retained_and_no_fresh_budget(self):
        from orchestrator import live_feedback as live
        async def failed(*args,**kwargs):raise RuntimeError('synthetic failure before any HTTP')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'fixed-round-2';b=stable_bytes(synthetic_snapshot(2))
            with patch.object(live,'OUTPUT',root),patch.object(live,'verified_input',return_value=b),patch.object(live,'run_feedback',side_effect=failed):
                with self.assertRaises(RuntimeError):asyncio.run(live.live('a'*64,'b'*64))
                self.assertTrue((root/'live-failure.json').exists())
                with self.assertRaises(FileExistsError):asyncio.run(live.live('a'*64,'b'*64))

    def test_legacy_generation_entry_denied(self):
        from orchestrator.local_research import run
        with self.assertRaisesRegex(ValueError,'verified post-experiment'):asyncio.run(run(None,None))

    def test_live_missing_input_never_constructs_transport(self):
        from orchestrator import live_feedback as live
        with patch.object(live,'verified_input',side_effect=FileNotFoundError('no real AI result')),patch.object(live.httpx,'AsyncHTTPTransport') as transport:
            with self.assertRaises(FileNotFoundError):asyncio.run(live.live('a'*64,'b'*64))
            transport.assert_not_called()

if __name__=='__main__':unittest.main()
