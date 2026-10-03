"""Real Omnigent SDK with in-memory transport; all model events are simulated."""
import asyncio,json,tempfile,unittest
from pathlib import Path
import httpx
from orchestrator.research_tools import ResearchCapabilities,stable_bytes,sha
from orchestrator.research_feedback import run_feedback,mock_transport,expected_comparison
from orchestrator.tests.test_research_tools import synthetic_snapshot

class SDKIntegration(unittest.TestCase):
    def test_sdk_registers_two_tools_and_calls_real_callbacks_in_mock_chain(self):
        async def check():
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);b=stable_bytes(synthetic_snapshot());cap=ResearchCapabilities(b,sha(b),root/'proposals',mode='cpu_mock')
                result=await run_feedback(cap,root,mock_transport(cap),mode='cpu_mock')
                self.assertEqual(result['real_model_generations'],0)
                self.assertEqual(result['mock_transport_requests'],5)
                self.assertEqual([c['tool'] for c in cap.audit],['read_ai_history','submit_experiment_proposal'])
                payloads=[json.loads(p.read_text())['payload'] for p in root.glob('request-*.json')]
                names={t['function']['name'] for b in payloads for t in b.get('tools',[])}
                self.assertEqual(names,{'read_ai_history','submit_experiment_proposal'})
                for before,after in [('Evaluator','Hypothesis'),('Hypothesis','Planner')]:
                    a=json.loads((root/f'{before}-validated.json').read_text());b=json.loads((root/f'{after}-input.json').read_text())
                    self.assertEqual(a['output_sha256'],b['previous_output']['output_sha256'])
                self.assertFalse(cap.receipt['training_dispatched'])
        asyncio.run(check())
    def test_non_mock_transport_rejected_before_any_model_call(self):
        async def check():
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);b=stable_bytes(synthetic_snapshot());cap=ResearchCapabilities(b,sha(b),root,mode='cpu_mock')
                with self.assertRaises(ValueError):await run_feedback(cap,root,object(),mode='cpu_mock')
        asyncio.run(check())
    def test_evaluator_depends_on_own_ai_outcome(self):
        data=synthetic_snapshot(2);data['records'][-1]['accuracy']=.9
        self.assertEqual(expected_comparison(data),'above_baseline_mean')
        data['records'][-1]['accuracy']=.4
        self.assertEqual(expected_comparison(data),'at_or_below_baseline_mean')
        data['records'][-1].update(status='timed_out',accuracy=None,loss=None)
        self.assertEqual(expected_comparison(data),'failed')
if __name__=='__main__':unittest.main()
