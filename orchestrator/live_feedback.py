"""Explicit real post-experiment entry. Never invokes mock or starts services."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,asyncio,json,subprocess,sys
from pathlib import Path
import httpx
from orchestrator.research_tools import ResearchCapabilities,sha
from orchestrator.research_feedback import run_feedback
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'recursive-scientist-local'
OUTPUT=PRIVATE/'g6-feedback/round-2'
CONTRACT=PRIVATE/'contract-venv/bin/python'

def verified_input(request_hash,result_hash):
    process=subprocess.run([str(CONTRACT),'-I','-B',str(ROOT/'orchestrator/feedback_input.py'),
        '--request-sha256',request_hash,'--result-sha256',result_hash],cwd=ROOT,
        check=True,capture_output=True)
    return process.stdout

async def live(request_hash,result_hash):
    data=verified_input(request_hash,result_hash)
    # One fixed production feedback budget, retained after failure. No caller path/quota.
    OUTPUT.mkdir(parents=True,exist_ok=False,mode=0o700)
    (OUTPUT/'verified-snapshot.json').write_bytes(data)
    cap=ResearchCapabilities(data,sha(data),OUTPUT/'proposals',mode='live')
    try:
        return await run_feedback(cap,OUTPUT,httpx.AsyncHTTPTransport(retries=0,trust_env=False),mode='live')
    except BaseException as exc:
        (OUTPUT/'live-failure.json').write_text(json.dumps({'type':type(exc).__name__,'status':'failed_no_retry_budget_retained'}))
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request-sha256',required=True);p.add_argument('--result-sha256',required=True)
    p.add_argument('--execute-live',action='store_true',required=True)
    a=p.parse_args();print(json.dumps(asyncio.run(live(a.request_sha256,a.result_sha256)),indent=2))
if __name__=='__main__':main()
