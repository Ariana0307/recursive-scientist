"""Controlled search entry. No G4 authorize command; examples are unexecutable drafts."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import argparse,json,os,signal,time,traceback
from runner.search_authority import SearchAuthority
from runner.search_plan import SearchPlan,EVALUATION_HASH
from runner.storage import AdmissionError,atomic_new,json_new,read_bytes
from runner.engine import check_checkout,check_environment,train_job
from runner.cli import now,result_payload
from runner.supervisor import supervise
from runner.model_artifact import publish_pending


def run(raw,authority=None):
    authority=authority if authority is not None else SearchAuthority.local()
    authority.load();check_environment()
    request,reservation=authority.reserve(raw)
    check_checkout(request)
    attempt=authority.campaign/f"start-{reservation['slot']}";attempt.mkdir(mode=0o700)
    atomic_new(attempt/'request.json',request.model_dump_json(indent=2).encode())
    atomic_new(attempt/'config.json',request.config.model_dump_json(indent=2).encode())
    started,start=now(),time.monotonic()
    json_new(attempt/'started.json',{'started_at':started,'reservation':reservation})
    status,metrics,device='failed',None,None
    error={'kind':'execution','message':'Search child did not produce a complete outcome.'};fd=None
    try:
        authority.load();fd=authority.capability(reservation)
        env=os.environ.copy();env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
        env.update(RS_SEARCH_CAP_FD=str(fd),CUBLAS_WORKSPACE_CONFIG=':4096:8',PYTHONDONTWRITEBYTECODE='1')
        with (attempt/'worker.log').open('xb') as log:
            state,_,code=supervise([sys.executable,'-I','-B',str(ROOT/'runner/search_cli.py'),'_child'],
                                 max(0,300-(time.monotonic()-start)),log,env,pass_fds=(fd,))
        if state=='timed_out' or time.monotonic()-start>=300:
            status,error='timed_out',{'kind':'timeout','message':'Search hard deadline exceeded.'}
        elif code==0:
            outcome=json.loads(read_bytes(attempt/'outcome.json'))
            status,metrics,error=outcome['status'],outcome['metrics'],outcome['error']
        else:error={'kind':'execution','message':f'Search child exit {code}; private evidence retained.'}
    except (KeyboardInterrupt,SystemExit):status,error='cancelled',{'kind':'cancelled','message':'Operator cancelled search attempt.'}
    except Exception as exc:
        atomic_new(attempt/'supervisor-error.txt',traceback.format_exc().encode())
        status,metrics,error='failed',None,{'kind':'execution','message':f'Search supervisor {type(exc).__name__}; slot retained.'}
    finally:
        if fd is not None:os.close(fd)
    if (attempt/'device.json').exists():device=json.loads(read_bytes(attempt/'device.json'))['actual_device']
    if status=='succeeded':
        try:
            # First validate the outcome; the success Result written LAST is the artifact commit marker.
            result_payload(request,status,started,time.monotonic()-start,device,metrics,error)
            publish_pending(attempt,request,EVALUATION_HASH)
        except (KeyboardInterrupt,SystemExit):
            status,metrics,error='cancelled',None,{'kind':'cancelled','message':'Cancelled during artifact finalization.'}
        except Exception as exc:
            status,metrics,error='failed',None,{'kind':'execution','message':f'State artifact validation/publication failed ({type(exc).__name__}).'}
    elapsed=time.monotonic()-start
    if elapsed>=300:
        status,metrics,error='timed_out',None,{'kind':'timeout','message':'Search finalization exceeded deadline.'}
    if status!='succeeded':metrics=None
    try:result=result_payload(request,status,started,elapsed,device,metrics,error)
    except Exception:result=result_payload(request,'failed',started,elapsed,device,error={'kind':'execution','message':'Invalid search outcome.'})
    # A crash/timeout before this commit never makes staged weights loadable as success.
    atomic_new(attempt/'result.json',result.model_dump_json(indent=2).encode())
    return result.model_dump(mode='json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['validate-plan','run','_child'])
    args=parser.parse_args();authority=SearchAuthority.local()
    if args.action=='validate-plan':
        print(json.dumps({'status':authority.plan.status,'plan_hash':authority.plan.digest(),
                          'max_starts':authority.plan.max_starts,'authorization_created':False}));return 0
    if args.action=='_child':
        request,attempt,receipt=authority.claim(int(os.environ['RS_SEARCH_CAP_FD']))
        check_checkout(request);packages=check_environment()
        train_job(request,packages,attempt,{'mode':'full','campaign_id':authority.plan.campaign_id,
                   'evaluation_sha256':EVALUATION_HASH,'save_state_dict':True})
        return 0
    def cancel(*args):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    raw=sys.stdin.buffer.read(16385)
    if len(raw)>16384:raise AdmissionError('parameter payload too large')
    result=run(raw,authority);print(json.dumps(result,indent=2))
    return 0 if result['status']=='succeeded' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'rejected','error_type':type(exc).__name__,
              'message':str(exc) if isinstance(exc,AdmissionError) else 'Closed plan or input validation failed.'}),file=sys.stderr)
        raise SystemExit(1)
