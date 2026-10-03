"""Two capabilities only. Trusted code supplies pinned, prevalidated AI history.

This module needs Pydantic only so the existing Omnigent environment can serve
snapshots produced by the separate, existing pinned contract environment.
"""
import hashlib
import json
from pathlib import Path
from typing import Literal,Annotated
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Closed(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False,frozen=True)
class Proposal(Closed):
    learning_rate:Literal[.0003,.001,.003]
    weight_decay:Literal[0.,.0001,.001]
    augmentation:Literal['none','basic']
    @model_validator(mode='before')
    @classmethod
    def no_bool(cls,v):
        if isinstance(v,dict) and any(type(v.get(k)) is bool for k in ('learning_rate','weight_decay')):raise ValueError('boolean rejected')
        return v
class ReadHistory(Closed):
    view:Literal['ai_visible_history']
Digest=Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]
class HistoryRecord(Closed):
    origin:Literal['baseline','ai']
    round:Annotated[int,Field(ge=0,le=6)]
    experiment_id:Annotated[str,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')]
    seed:Annotated[int,Field(ge=0,le=2**32-1)]
    parameters:Proposal
    status:Literal['succeeded','failed','timed_out','cancelled']
    accuracy:Annotated[float,Field(ge=0,le=1)]|None
    loss:Annotated[float,Field(ge=0)]|None
    code_version:Annotated[str,Field(pattern=r'^[0-9a-f]{40}$')]
    config_hash:Digest
    request_sha256:Digest
    result_sha256:Digest
    @model_validator(mode='after')
    def metrics(self):
        if self.status=='succeeded':
            if self.accuracy is None or self.loss is None:raise ValueError('success needs actual metrics')
        elif self.accuracy is not None or self.loss is not None:raise ValueError('failed metrics must be null')
        return self
class VisibleHistory(Closed):
    schema_version:Literal['ai-visible-v1']
    current_round:Annotated[int,Field(ge=1,le=6)]
    records:list[HistoryRecord]
    verification:Literal['full_contract_request_result_hash_split']
    random_visible:Literal[False]
    @model_validator(mode='after')
    def temporal_boundary(self):
        baseline=[r for r in self.records if r.origin=='baseline'];ai=[r for r in self.records if r.origin=='ai']
        if sorted(r.seed for r in baseline)!=[42,43,44] or any(r.round!=0 for r in baseline):raise ValueError('baseline identity')
        if sorted(r.round for r in ai)!=list(range(1,self.current_round)):raise ValueError('missing, duplicate or future AI history')
        if len({r.experiment_id for r in self.records})!=len(self.records):raise ValueError('duplicate result identity')
        return self

def sha(data):return hashlib.sha256(data).hexdigest()
def stable_bytes(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

class ResearchCapabilities:
    def __init__(self,snapshot_bytes,expected_sha256,output_dir,*,mode):
        if mode not in ('cpu_mock','future_authorized'):raise ValueError('explicit execution mode required')
        if sha(snapshot_bytes)!=expected_sha256:raise ValueError('trusted snapshot digest mismatch')
        self._history=VisibleHistory.model_validate_json(snapshot_bytes)
        self._history_bytes=self._history.model_dump_json().encode()
        self.snapshot_hash=expected_sha256;self.mode=mode
        self.output=Path(output_dir);self.output.mkdir(parents=True,exist_ok=True)
        self.phase='Evaluator';self.receipt=None;self.audit=[]

    @staticmethod
    def specs():
        return [dict(name='read_ai_history',description='Read only verified common baseline and completed AI history; no Random/test evidence.',parameters=ReadHistory.model_json_schema()),
                dict(name='submit_experiment_proposal',description='Submit allowed hyperparameters as an unapproved proposal only; never authorizes or dispatches training.',parameters=Proposal.model_json_schema())]

    def allowed_specs(self):
        return self.specs() if self.phase=='Planner' else self.specs()[:1]

    async def dispatch(self,name,args):
        if name not in {s['name'] for s in self.allowed_specs()}:raise ValueError('tool not allowed for this role')
        if name=='read_ai_history':
            ReadHistory.model_validate(args)
            result=json.loads(self._history_bytes)
        else:
            p=Proposal.model_validate(args);parameters=p.model_dump()
            n=self._history.current_round
            if n==1 and parameters!={'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}:
                raise ValueError('AI trial 1 must preserve the real G4 proposal')
            record={'task_id':'RS-20261004-G5','revision':'r1','status':'proposed_not_authorized','mode':self.mode,'round':n,'seed':41+n,
                    'worker_id':'worker-02' if n%2 else 'worker-01','role':'02_deploy' if n%2 else '01_train',
                    'parameters':parameters,'history_sha256':self.snapshot_hash,'training_dispatched':False}
            record['proposal_id']='proposal-'+sha(stable_bytes(record))[:24]
            target=self.output/f'ai-round-{n}-proposal.json'
            encoded=stable_bytes(record)
            if target.exists():
                if target.read_bytes()!=encoded:raise ValueError('conflicting proposal already exists; no overwrite')
            else:
                with target.open('xb') as f:f.write(encoded)
            self.receipt=record
            result={k:record[k] for k in ('proposal_id','status','training_dispatched','mode')}
        self.audit.append({'phase':self.phase,'tool':name,'arguments':args,'result_sha256':sha(stable_bytes(result)),'mode':self.mode})
        return result

    def register(self,executor):
        # Omnigent 0.16.0 _build_tools constructs SDK FunctionTool callbacks that
        # invoke this exact _tool_executor hook. Version-pinned, covered by SDK tests.
        executor._tool_executor=self.dispatch
        return self.allowed_specs()
