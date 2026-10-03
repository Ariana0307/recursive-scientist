"""Bounded Omnigent SDK role sequencing through a loopback-only gateway.

Trusted controller owns file access. Model agents have no tools or handoffs that
execute code. Validated role output is explicitly supplied to the next session.
This is a research role chain, not an experiment feedback loop.
"""
from __future__ import annotations
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import httpx

MODEL = 'qwen3:4b'
MAX_REQUESTS = 6
MAX_TOKENS = 1000
TIMEOUT = 120


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Ready(Closed):
    status: Literal['OMNIGENT_READY']


class Evidence(Closed):
    role: Literal['Evidence']
    finding: Literal['three_seed_baseline_only']
    threshold: Literal['exploratory_not_significance']
    causal_claim: Literal['no_variable_effect_established']
    next_step: Literal['controlled_search_needed']


class Choice(Closed):
    variable: Literal['learning_rate', 'weight_decay', 'augmentation']
    direction: Literal['lower', 'higher', 'enable', 'disable']

    @model_validator(mode='after')
    def paired_direction(self):
        allowed = ('enable', 'disable') if self.variable == 'augmentation' else ('lower', 'higher')
        if self.direction not in allowed:
            raise ValueError('direction does not match variable')
        # Baseline has no augmentation; disabling it would not explore a new setting.
        if self.variable == 'augmentation' and self.direction == 'disable':
            raise ValueError('baseline already has augmentation disabled')
        return self


class Candidate(Choice):
    hypothesis_id: Literal['H1', 'H2']
    prediction: Literal['validation_accuracy_may_increase', 'validation_accuracy_may_decrease', 'effect_uncertain']


class Hypothesis(Closed):
    role: Literal['Hypothesis']
    candidates: list[Candidate] = Field(min_length=2, max_length=2)
    uncertainty: Literal['untested_no_causal_evidence']

    @model_validator(mode='after')
    def unique(self):
        if {c.hypothesis_id for c in self.candidates} != {'H1', 'H2'}:
            raise ValueError('two distinct hypothesis identities required')
        if len({(c.variable,c.direction) for c in self.candidates}) != 2:
            raise ValueError('two distinct candidate directions required')
        return self


class Planner(Choice):
    role: Literal['Planner']
    hypothesis_id: Literal['H1', 'H2']
    action: Literal['propose_only_no_dispatch']


def sample_proposal(plan: Planner, hypotheses: Hypothesis, seed=20261004):
    chosen = next(c for c in hypotheses.candidates if c.hypothesis_id == plan.hypothesis_id)
    if (chosen.variable, chosen.direction) != (plan.variable, plan.direction):
        raise ValueError('planner changed the referenced hypothesis')
    base = {'learning_rate':.001, 'weight_decay':.0001, 'augmentation':'none'}
    space = {'learning_rate':[.0003,.001,.003], 'weight_decay':[0.,.0001,.001], 'augmentation':['none','basic']}
    v,d = plan.variable,plan.direction
    options = ([x for x in space[v] if x < base[v]] if d == 'lower' else
               [x for x in space[v] if x > base[v]] if d == 'higher' else ['basic'])
    base[v] = random.Random(seed).choice(options)
    return {'status':'proposed_not_authorized', 'sampler':'Python random.Random.choice', 'sampler_seed':seed,
            'selection':plan.model_dump(), 'parameters':dict(base,epochs=3,batch_size=128,split_seed=20261003,
             model='small-cnn-v1',dataset='cifar10-python-v1'), 'training_dispatched':False}


class TimedStream(httpx.AsyncByteStream):
    def __init__(self, stream, deadline, raw_path):
        self.stream,self.deadline,self.raw_path=stream,deadline,raw_path

    async def __aiter__(self):
        try:
            with self.raw_path.open('xb') as f:
                async with asyncio.timeout_at(self.deadline):
                    async for chunk in self.stream:
                        f.write(chunk); f.flush()
                        yield chunk
        finally:
            await self.stream.aclose()

    async def aclose(self):
        await self.stream.aclose()


class GuardedTransport(httpx.AsyncBaseTransport):
    """Checks every generation dispatch, including SDK/Omnigent internal retries."""
    def __init__(self, root, inner=None):
        self.root = root
        self.inner = inner or httpx.AsyncHTTPTransport(retries=0, trust_env=False)
        self.role = 'unset'
        self.schema = None
        self.executor = None

    async def handle_async_request(self, request):
        u = request.url
        if (u.scheme,u.host,u.port,u.path) != ('http','127.0.0.1',11434,'/v1/chat/completions') or u.query:
            raise ValueError('non-allowlisted gateway destination')
        body = json.loads(await request.aread())
        if request.method != 'POST' or body.get('model') != MODEL:
            raise ValueError('non-allowlisted model request')
        if body.get('tools') or body.get('functions'):
            raise ValueError('tools forbidden')
        if type(body.get('max_tokens')) is not int or not 1 <= body['max_tokens'] <= MAX_TOKENS:
            raise ValueError('serialized token cap absent or too high')
        limits = request.extensions.get('timeout',{})
        if not limits or any(v is None or v>TIMEOUT or v<=0 for v in limits.values()):
            raise ValueError('transport timeout missing or too high')
        if body.get('reasoning_effort') != 'none':
            raise ValueError('thinking must be explicitly disabled')
        if self.executor is not None:
            states = list(self.executor._session_states.values())
            if not states or any(s.agent is None or s.agent.tools or s.agent.handoffs or s.agent.mcp_servers for s in states):
                raise ValueError('actual SDK agent exposes unexpected capabilities')
        # Official OpenAI-compatible structured-output field; added by trusted controller.
        if self.schema is not None:
            body['response_format']={'type':'json_schema','json_schema':{'name':self.role,'strict':True,'schema':self.schema}}
        body['stream_options'] = {'include_usage': True}
        body['temperature'] = 0
        raw = json.dumps(body,allow_nan=False).encode()
        headers = dict(request.headers); headers.pop('content-length',None)
        outgoing = httpx.Request('POST',request.url,headers=headers,content=raw,extensions=request.extensions)
        with (self.root/'budget.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            existing = sorted(self.root.glob('request-*.json'))
            if len(existing)>=MAX_REQUESTS: raise ValueError('six generation request budget exhausted')
            n=len(existing)+1
            save(self.root/f'request-{n:02}.json',{'number':n,'role':self.role,'model':MODEL,
                 'max_tokens':body['max_tokens'],'timeout_seconds':TIMEOUT,'tool_count':0,
                 'payload':body,'payload_sha256':hashlib.sha256(raw).hexdigest()})
        deadline=asyncio.get_running_loop().time()+TIMEOUT
        try:
            async with asyncio.timeout_at(deadline): response=await self.inner.handle_async_request(outgoing)
        except Exception as exc:
            save(self.root/f'error-{n:02}.json',{'error_type':type(exc).__name__,'message':str(exc)})
            raise
        return httpx.Response(response.status_code,headers=response.headers,
            stream=TimedStream(response.stream,deadline,self.root/f'response-{n:02}.raw'),extensions=response.extensions)

    async def aclose(self):
        await self.inner.aclose()


async def run(root, baseline):
    os.environ['OMNIGENT_DATA_DIR'] = str(root/'omnigent-state')
    from openai import AsyncOpenAI
    from omnigent.inner.openai_agents_sdk_executor import OpenAIAgentsSDKExecutor
    from omnigent.inner.executor import ExecutorConfig, TextChunk, ExecutorError
    from omnigent.spec.types import RetryPolicy
    # Existing output is never reset. Each run gets a fresh session, same durable budget.
    attempt=root/f'attempt-{time.time_ns()}'
    attempt.mkdir()
    transport=GuardedTransport(root)
    http=httpx.AsyncClient(transport=transport,timeout=TIMEOUT,trust_env=False)
    client=AsyncOpenAI(base_url='http://127.0.0.1:11434/v1',api_key='ollama-local',max_retries=0,
                       timeout=TIMEOUT,http_client=http)
    executor=OpenAIAgentsSDKExecutor(client=client,use_responses=False,model=MODEL,
                    retry_policy=RetryPolicy(max_retries=0,timeout_per_request_s=TIMEOUT))
    transport.executor=executor
    previous=None
    async def turn(role,payload,schema=None):
        nonlocal previous
        transport.role=role
        transport.schema=schema.model_json_schema() if schema else None
        session=f'G4-{attempt.name}-{role}'
        inp={'role':role,'session_id':session,'previous_output':previous,'data':payload}
        save(attempt/f'{role}-input.json',inp)
        instruction=('You are the '+role+' research role. /no_think\n'
          'Use only supplied evidence. Return only the required JSON object, no markdown. '
          'A proposal is untested. Never claim a variable is effective from baseline-only data. '
          'Select variables/directions only, no numeric hyperparameters. '
          'Use the predecessor output; do not change its meaning.\n')
        if schema: instruction+='Required JSON schema: '+json.dumps(schema.model_json_schema())
        else: instruction='Return exactly OMNIGENT_READY and nothing else. /no_think'
        text='';events=[]
        try:
            async with asyncio.timeout(TIMEOUT):
                async for event in executor.run_turn(
                    [{'role':'user','content':json.dumps(inp),'session_id':session}],[],instruction,
                    ExecutorConfig(model=MODEL,max_tokens=MAX_TOKENS,extra={'max_tokens':MAX_TOKENS,
                      'max_turns':1,'reasoning_effort':'none','parallel_tool_calls':False})):
                    events.append(type(event).__name__)
                    if isinstance(event,TextChunk):text+=event.text
                    if isinstance(event,ExecutorError):raise RuntimeError(event.message)
            (attempt/f'{role}-raw.txt').write_text(text)
            save(attempt/f'{role}-events.json',events)
            parsed=schema.model_validate_json(text) if schema else None
            if schema is None and text.strip()!='OMNIGENT_READY':raise ValueError('READY response mismatch')
            output=parsed.model_dump() if parsed else {'text':text.strip()}
            record={'role':role,'session_id':session,'model':MODEL,'input_sha256':digest(inp),
                    'previous_output_reference':previous,'output':output,'output_sha256':digest(output)}
            save(attempt/f'{role}-validated.json',record)
            previous={'role':role,'session_id':session,'output_sha256':digest(output),'output':output}
            return parsed
        except Exception as exc:
            (attempt/f'{role}-raw.txt').write_text(text)
            save(attempt/f'{role}-failure.json',{'type':type(exc).__name__,'message':str(exc),'events':events})
            raise
    try:
        await turn('Ready',{'request':'Return status OMNIGENT_READY as JSON'},Ready)
        previous=None
        await turn('Evidence',baseline,Evidence)
        hypotheses=await turn('Hypothesis',{'baseline':baseline,'requirement':'two distinct testable exploratory directions with predictions'},Hypothesis)
        plan=await turn('Planner',{'requirement':'choose exactly one predecessor hypothesis without changing its variable or direction'},Planner)
        save(attempt/'sampled-proposal.json',sample_proposal(plan,hypotheses))
        save(attempt/'outcome.json',{'status':'role_chain_passed','experiment_feedback_loop':'not_verified',
                                  'requests_total':len(list(root.glob('request-*.json'))),'training_dispatched':False})
    finally:
        await executor.close()
        await client.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(mode=0o700,parents=True,exist_ok=True)
    asyncio.run(run(args.output,json.loads(args.baseline.read_text())))

if __name__=='__main__':main()
