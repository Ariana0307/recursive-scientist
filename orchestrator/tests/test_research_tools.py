"""Synthetic CPU fixtures only; no model, network, authority, data or GPU calls."""
import asyncio,json,tempfile,unittest,copy
from pathlib import Path
from pydantic import ValidationError
from orchestrator.research_tools import ResearchCapabilities,Proposal,sha,stable_bytes

def synthetic_snapshot(round_number=1,score=.7):
    def row(seed,origin='baseline',n=0):return {'origin':origin,'round':n,'experiment_id':f'SYNTHETIC-{origin}-{seed}','seed':seed,
      'parameters':{'learning_rate':.001,'weight_decay':.0001,'augmentation':'none'},'status':'succeeded','accuracy':score,'loss':1.,
      'code_version':'a'*40,'config_hash':'b'*64,'request_sha256':'c'*64,'result_sha256':'d'*64}
    return {'schema_version':'ai-visible-v1','current_round':round_number,'records':[row(s) for s in (42,43,44)]+[row(41+n,'ai',n) for n in range(1,round_number)],'verification':'full_contract_request_result_hash_split','random_visible':False}

class ToolBoundary(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    def cap(self,obj=None):
        b=stable_bytes(obj or synthetic_snapshot());return ResearchCapabilities(b,sha(b),Path(self.tmp.name)/'proposals',mode='cpu_mock')
    def call(self,cap,name,args):return asyncio.run(cap.dispatch(name,args))
    def test_no_arbitrary_selectors(self):
        c=self.cap()
        for key in ('path','command','seed','budget','authorize','experiment_id','arm'):
            with self.assertRaises(ValidationError):self.call(c,'read_ai_history',{'view':'ai_visible_history',key:'hidden'})
        with self.assertRaises(ValueError):self.call(c,'shell',{})
        with self.assertRaises(ValidationError):self.call(c,'read_ai_history',{})
    def test_digest_random_future_and_partial_history_rejected(self):
        b=stable_bytes(synthetic_snapshot())
        with self.assertRaises(ValueError):ResearchCapabilities(b,'0'*64,self.tmp.name,mode='cpu_mock')
        for edit in ('random','future','missing'):
            obj=synthetic_snapshot(2)
            if edit=='random':obj['records'][-1]['origin']='random'
            if edit=='future':obj['records'][-1]['round']=2
            if edit=='missing':obj['records'].pop()
            with self.assertRaises(ValueError):self.cap(obj)
    def test_reads_only_copy_of_visible_verified_history(self):
        c=self.cap();a=self.call(c,'read_ai_history',{'view':'ai_visible_history'})
        a['records'].clear()
        b=self.call(c,'read_ai_history',{'view':'ai_visible_history'})
        self.assertEqual(len(b['records']),3);self.assertFalse(b['random_visible'])
    def test_proposal_forbidden_fields_ranges_and_nonfinite(self):
        c=self.cap();c.phase='Planner';base={'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}
        for key in ('seed','budget','command','path','authorization','epochs','batch_size'):
            with self.assertRaises(ValidationError):self.call(c,'submit_experiment_proposal',dict(base,**{key:1}))
        for value in (float('nan'),float('inf'),True,.1):
            with self.assertRaises(ValueError):self.call(c,'submit_experiment_proposal',dict(base,learning_rate=value))
        self.assertEqual(list(c.output.iterdir()),[])
    def test_phase_initial_proposal_and_idempotence(self):
        c=self.cap();base={'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}
        with self.assertRaises(ValueError):self.call(c,'submit_experiment_proposal',base)
        c.phase='Planner'
        with self.assertRaises(ValueError):self.call(c,'submit_experiment_proposal',dict(base,learning_rate=.0003))
        first=self.call(c,'submit_experiment_proposal',base);again=self.call(c,'submit_experiment_proposal',base)
        self.assertEqual(first,again);self.assertFalse(first['training_dispatched'])
        self.assertEqual(c.receipt['worker_id'],'worker-02');self.assertEqual(c.receipt['seed'],42)
    def test_next_round_binds_context_and_retains_conflicts(self):
        c=self.cap(synthetic_snapshot(2));c.phase='Planner';p={'learning_rate':.0003,'weight_decay':0.,'augmentation':'basic'}
        self.call(c,'submit_experiment_proposal',p)
        self.assertEqual((c.receipt['worker_id'],c.receipt['seed']),('worker-01',43))
        before=next(c.output.iterdir()).read_bytes()
        with self.assertRaises(ValueError):self.call(c,'submit_experiment_proposal',dict(p,learning_rate=.003))
        self.assertEqual(before,next(c.output.iterdir()).read_bytes())
    def test_exact_closed_tool_specs(self):
        specs=ResearchCapabilities.specs();self.assertEqual([s['name'] for s in specs],['read_ai_history','submit_experiment_proposal'])
        for s in specs:self.assertFalse(s['parameters']['additionalProperties'])
        self.assertEqual(set(specs[1]['parameters']['properties']),{'learning_rate','weight_decay','augmentation'})
if __name__=='__main__':unittest.main()
