"""Actual Omnigent SDK entry point with explicit injected transport.

The CLI ONLY runs CPU/mock. It cannot select a real network transport. Future
real execution needs separate authorization and a trusted caller providing it.
No HandoffTool, authorizer, runner or training imports exist here.
"""
import argparse,asyncio,json,os
from pathlib import Path
from typing import Literal
import httpx
from pydantic import model_validator
from orchestrator.research_tools import Closed,ResearchCapabilities,sha,stable_bytes
from orchestrator.local_research import GuardedTransport,Hypothesis,Planner as DirectionPlan,sample_proposal

class Evaluation(Closed):
    role:Literal['Evaluator']
    comparison:Literal['baseline_only','above_baseline_mean','at_or_below_baseline_mean','failed']
    interpretation:Literal['exploratory_not_significance']
class PlanReceipt(Closed):
    role:Literal['Planner']
    hypothesis_id:Literal['H1','H2']
    proposal_id:str
    status:Literal['proposed_not_authorized']

def expected_comparison(history):
    records=history['records'];ai=[r for r in records if r['origin']=='ai']
    if not ai:return 'baseline_only'
    last=max(ai,key=lambda r:r['round'])
    if last['status']!='succeeded':return 'failed'
    baseline=[r['accuracy'] for r in records if r['origin']=='baseline']
    return 'above_baseline_mean' if last['accuracy']>sum(baseline)/len(baseline) else 'at_or_below_baseline_mean'

def put(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

async def run_feedback(capabilities,root,inner_transport,*,mode):
    if mode!=capabilities.mode:raise ValueError('execution mode mismatch')
    if mode=='cpu_mock' and not isinstance(inner_transport,httpx.MockTransport):raise ValueError('mock mode requires in-memory transport')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    os.environ['OMNIGENT_DATA_DIR']=str(root/'omnigent-state')
    from importlib.metadata import version
    if version('omnigent')!='0.16.0':raise RuntimeError('registered interface is pinned to Omnigent 0.16.0')
    from openai import AsyncOpenAI
    from omnigent.inner.openai_agents_sdk_executor import OpenAIAgentsSDKExecutor
    from omnigent.inner.executor import ExecutorConfig,TextChunk,ExecutorError
    from omnigent.spec.types import RetryPolicy
    transport=GuardedTransport(root,inner_transport,allowed_tool_names=[s['name'] for s in capabilities.specs()])
    client=AsyncOpenAI(base_url='http://127.0.0.1:11434/v1',api_key='local-unused',max_retries=0,timeout=120,
        http_client=httpx.AsyncClient(transport=transport,timeout=120,trust_env=False))
    executor=OpenAIAgentsSDKExecutor(client=client,use_responses=False,model='qwen3:4b',retry_policy=RetryPolicy(max_retries=0,timeout_per_request_s=120))
    transport.executor=executor;previous=None;hypotheses=None;sampled={}
    try:
        for role,schema in [('Evaluator',Evaluation),('Hypothesis',Hypothesis),('Planner',PlanReceipt)]:
            capabilities.phase=role;specs=capabilities.register(executor)
            transport.role=role;transport.schema=schema.model_json_schema()
            session='G5-'+root.name+'-'+role
            # No worker plan, random catalog, hidden arm result, or path enters input.
            inp={'role':role,'mode':mode,'previous_output':previous,'history_sha256':capabilities.snapshot_hash}
            if role=='Planner':inp['trusted_sampled_candidates']=sampled
            put(root/f'{role}-input.json',inp)
            instruction=('ROLE='+role+'\nUse only read_ai_history and validated predecessor evidence. '
              'Never access Random/test data, grant authorization or train. Return JSON matching '+json.dumps(schema.model_json_schema())+'. '
              'Evaluator must call read_ai_history before evaluating. Hypothesis proposes two distinct exploratory directions. '
              'Planner must submit one trusted sampled candidate via submit_experiment_proposal, then return its actual receipt. '
              'When current AI round is 1, preserve learning_rate=.003, weight_decay=.0001, augmentation=none. /no_think')
            text='';events=[]
            try:
                async with asyncio.timeout(120):
                    async for event in executor.run_turn([{'role':'user','content':json.dumps(inp),'session_id':session}],specs,instruction,
                        ExecutorConfig(model='qwen3:4b',max_tokens=1000,extra={'max_tokens':1000,'max_turns':3,'reasoning_effort':'none','parallel_tool_calls':False})):
                        events.append(type(event).__name__)
                        if isinstance(event,TextChunk):text+=event.text
                        if isinstance(event,ExecutorError):raise RuntimeError(event.message)
                (root/f'{role}-raw.txt').write_text(text)
                parsed=schema.model_validate_json(text)
                if role=='Evaluator':
                    if not any(x['phase']==role and x['tool']=='read_ai_history' for x in capabilities.audit):raise ValueError('Evaluator did not read verified history')
                    if parsed.comparison!=expected_comparison(json.loads(capabilities._history_bytes)):raise ValueError('Evaluator contradicts verified metrics')
                if role=='Hypothesis':
                    hypotheses=parsed
                    for candidate in parsed.candidates:
                        d=DirectionPlan(role='Planner',hypothesis_id=candidate.hypothesis_id,variable=candidate.variable,direction=candidate.direction,action='propose_only_no_dispatch')
                        proposal=sample_proposal(d,parsed)['parameters']
                        sampled[candidate.hypothesis_id]={k:proposal[k] for k in ('learning_rate','weight_decay','augmentation')}
                if role=='Planner':
                    receipt=capabilities.receipt
                    if receipt is None or parsed.proposal_id!=receipt['proposal_id'] or receipt['parameters']!=sampled[parsed.hypothesis_id]:raise ValueError('Planner receipt/hypothesis mismatch')
                record={'role':role,'session_id':session,'mode':mode,'model':'qwen3:4b','previous_output':previous,
                   'input_sha256':sha(stable_bytes(inp)),'output':parsed.model_dump(),'events':events}
                record['output_sha256']=sha(stable_bytes(record['output']))
                put(root/f'{role}-validated.json',record)
                previous={k:record[k] for k in ('role','session_id','output','output_sha256')}
            except Exception as exc:
                (root/f'{role}-raw.txt').write_text(text)
                put(root/f'{role}-failure.json',{'type':type(exc).__name__,'message':str(exc),'mode':mode,'events':events})
                raise
        result={'status':'passed','mode':mode,'real_model_generations':0 if mode=='cpu_mock' else len(list(root.glob('request-*.json'))),
                'mock_transport_requests':len(list(root.glob('request-*.json'))) if mode=='cpu_mock' else 0,
                'registered_tools':[s['name'] for s in capabilities.specs()],'training_started':False,'authorization_created':False,
                'handoff_mechanism':'trusted program passing validated outputs; no HandoffTool'}
        put(root/'outcome.json',result);return result
    finally:
        put(root/'tool-calls.json',capabilities.audit)
        await executor.close();await client.close()

def mock_transport(capabilities):
    def handle(request):
        body=json.loads(request.content)
        system=next(m['content'] for m in body['messages'] if m['role']=='system')
        role=system.split('ROLE=',1)[1].split('\n',1)[0]
        tool_seen=any(m['role']=='tool' for m in body['messages'])
        if role=='Evaluator' and not tool_seen:
            delta={'role':'assistant','tool_calls':[{'index':0,'id':'mock-read','type':'function','function':{'name':'read_ai_history','arguments':json.dumps({'view':'ai_visible_history'})}}]};finish='tool_calls'
        elif role=='Planner' and not tool_seen:
            delta={'role':'assistant','tool_calls':[{'index':0,'id':'mock-submit','type':'function','function':{'name':'submit_experiment_proposal','arguments':json.dumps({'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'})}}]};finish='tool_calls'
        else:
            if role=='Evaluator':obj={'role':role,'comparison':expected_comparison(json.loads(capabilities._history_bytes)),'interpretation':'exploratory_not_significance'}
            elif role=='Hypothesis':obj={'role':role,'candidates':[{'hypothesis_id':'H1','variable':'learning_rate','direction':'higher','prediction':'validation_accuracy_may_increase'},{'hypothesis_id':'H2','variable':'weight_decay','direction':'lower','prediction':'effect_uncertain'}],'uncertainty':'untested_no_causal_evidence'}
            else:obj={'role':role,'hypothesis_id':'H1','proposal_id':capabilities.receipt['proposal_id'],'status':'proposed_not_authorized'}
            delta={'role':'assistant','content':json.dumps(obj)};finish='stop'
        events=[{'id':'cpu-mock','object':'chat.completion.chunk','created':1,'model':'qwen3:4b','choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                {'id':'cpu-mock','object':'chat.completion.chunk','created':1,'model':'qwen3:4b','choices':[{'index':0,'delta':{},'finish_reason':finish}]}]
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=(''.join('data: '+json.dumps(e)+'\n\n' for e in events)+'data: [DONE]\n\n').encode())
    return httpx.MockTransport(handle)

def main():
    p=argparse.ArgumentParser(description='CPU/mock only. No real model endpoint is invoked.')
    p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--snapshot-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    cap=ResearchCapabilities(a.snapshot.read_bytes(),a.snapshot_sha256,a.output/'proposals',mode='cpu_mock')
    print(json.dumps(asyncio.run(run_feedback(cap,a.output,mock_transport(cap),mode='cpu_mock')),indent=2))
if __name__=='__main__':main()
