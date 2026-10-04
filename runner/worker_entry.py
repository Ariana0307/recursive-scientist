"""Use the accepted existing pinned worker venv, then exec the isolated G6 entry.
No environment creation, downloads, preflight data reads, or GPU initialization.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def select_python(explicit=None):
    if explicit:
        if not Path(explicit).is_absolute():raise RuntimeError('interpreter must be an absolute existing path')
        candidates=[Path(explicit)]
    else:raise RuntimeError('explicit accepted interpreter required')
    valid=[]
    probe='import sys;sys.path.insert(0,'+repr(str(ROOT))+');from runner.engine import check_environment;check_environment()'
    for path in candidates:
        if not path.is_file():continue
        result=subprocess.run([str(path),'-I','-B','-c',probe],capture_output=True,timeout=20)
        if result.returncode==0:valid.append(path)
    if len(valid)!=1:raise RuntimeError('need exactly one existing pinned worker Python; provide --python /absolute/path (no install)')
    return str(valid[0])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python');p.add_argument('action',choices=['authorize-first','extend','run-first','inspect'])
    p.add_argument('--worker',required=True,choices=['worker-01','worker-02'])
    p.add_argument('--operator');p.add_argument('--reason');p.add_argument('--through-slot',type=int)
    a=p.parse_args()
    accepted={'worker-01':'/home/lc/recursive-scientist-local/.venv-g1-py312/bin/python',
              'worker-02':'/home/lc/recursive-scientist-local/reference/env-g2/bin/python'}
    python=select_python(a.python or accepted[a.worker])
    if a.action=='inspect':
        print(json.dumps({'python':python,'checkout':str(ROOT),'worker':a.worker}));return
    if a.action=='run-first':
        # Bind expected worker in trusted launcher, not model-controlled parameters.
        script='import sys,json;sys.path.insert(0,'+repr(str(ROOT))+');from runner.search_authority import SearchAuthority;from runner.search_cli import main;from runner.storage import AdmissionError;a=SearchAuthority.local();assert a.worker_id=='+repr(a.worker)+', "worker mismatch";assert not a.slots(), "first slot already reserved";sys.argv=["search_cli.py","run"];raise SystemExit(main())'
        os.execv(python,[python,'-I','-B','-c',script])
    if not a.operator or not a.reason or a.through_slot is None:p.error('operator, reason and through-slot are required for explicit approval')
    os.execv(python,[python,'-I','-B',str(ROOT/'runner/release_cli.py'),a.action,'--worker',a.worker,
                    '--operator',a.operator,'--reason',a.reason,'--through-slot',str(a.through_slot)])
if __name__=='__main__':main()
