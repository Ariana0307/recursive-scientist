"""Independent search authority using G3 lock/journal/sealed-one-use mechanisms."""
import datetime
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
from runner import campaign as legacy
from runner.search_plan import SearchPlan, EVALUATION_HASH, Parameters, bind_request
from runner.storage import AdmissionError, atomic_new, json_new, lock, read_bytes, safe_dir
from schemas.contracts import ExperimentConfig,Result,match_result

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path.home()/'recursive-scientist-local'
PLAN_FILES={'worker-01':ROOT/'runner/plans/search-worker-01.json',
            'worker-02':ROOT/'runner/plans/search-worker-02.json'}


class SearchAuthority:
    def __init__(self,plan,worker_id,role,private_root=None):
        # Constructor belongs to trusted operator code, not model JSON.
        self.plan=SearchPlan.model_validate_json(plan.model_dump_json())
        self.worker_id,self.role=worker_id,role
        if (self.plan.worker_id,self.plan.role)!=(worker_id,role):raise AdmissionError('worker/role mismatch')
        self.private=Path(private_root) if private_root is not None else PRIVATE
        self.campaign=self.private/'search-campaigns'/self.plan.campaign_id
        self.authority=self.private/'search-authority'/self.plan.campaign_id
        # Independent of campaign names and both historical budget directories.
        self.fence=self.private/'search-execution-g6'/self.worker_id

    @classmethod
    def local(cls):
        # G4's local binding is operator-owned code. Other workers use the same class
        # with an explicit trusted binding, never a model-controlled selector.
        binding_path=PRIVATE/'search-worker-binding.json'
        worker,role='worker-01','01_train'
        if binding_path.exists() or binding_path.is_symlink():
            from schemas.contracts import ClosedModel, Identifier
            from typing import Literal
            class Binding(ClosedModel):
                worker_id: Literal['worker-01','worker-02']
                role: Identifier
            if binding_path.is_symlink():raise AdmissionError('worker binding symlink')
            st=binding_path.stat()
            if st.st_uid!=os.getuid() or st.st_mode & 0o077:raise AdmissionError('worker binding must be operator-private')
            binding=Binding.model_validate_json(read_bytes(binding_path))
            worker,role=binding.worker_id,binding.role
        plan=SearchPlan.model_validate_json(read_bytes(PLAN_FILES[worker]))
        return cls(plan,worker,role)

    def expected(self):
        if hashlib.sha256(read_bytes(ROOT/'runner/evaluate.py')).hexdigest()!=EVALUATION_HASH:
            raise AdmissionError('frozen evaluator changed')
        return {'plan':self.plan.model_dump(mode='json'),'plan_hash':self.plan.digest(),
                'code_commit':legacy.current_commit(),'worker_id':self.worker_id,'role':self.role}

    def secure(self,path):
        for node in (path,*path.parents):
            if node.is_symlink():raise AdmissionError('search authority symlink rejected')
            if node==self.private:break
        st=path.stat()
        if st.st_uid!=os.getuid() or st.st_mode & 0o022:raise AdmissionError('unsafe authority ownership/mode')

    def key(self):
        self.secure(self.authority)
        p=self.authority/'signing.key';self.secure(p)
        if p.stat().st_mode & 0o077:raise AdmissionError('unsafe signing key permissions')
        return read_bytes(p)

    def sign(self,obj):
        return {'payload':obj,'hmac_sha256':hmac.new(self.key(),legacy.canonical(obj),hashlib.sha256).hexdigest()}

    def verify(self,obj):
        if set(obj)!={'payload','hmac_sha256'} or not hmac.compare_digest(obj['hmac_sha256'],self.sign(obj['payload'])['hmac_sha256']):
            raise AdmissionError('search signature mismatch')
        return obj['payload']

    def frozen_identity(self):
        freeze=json.loads(read_bytes(ROOT/'configs/g5/freeze-manifest.json'))
        if self.plan.digest()!=freeze['plan_hashes'][self.worker_id]:
            raise AdmissionError('G5 frozen plan identity mismatch')

    def mirrored(self,name):
        raw=read_bytes(self.fence/name)
        if any(read_bytes(p/name)!=raw for p in (self.authority,self.campaign)):
            raise AdmissionError('persistent fence mirror mismatch')
        return self.verify(json.loads(raw))

    def append_mirrored(self,name,payload):
        receipt=self.sign(payload)
        # A crash leaves a detectable mismatch, never a fresh allowance.
        for root in (self.fence,self.authority,self.campaign):json_new(root/name,receipt)

    def released_through(self):
        self.secure(self.fence)
        names=[p.name for p in sorted(self.fence.glob('release-*.json'))]
        if not names or any(names!=[p.name for p in sorted(root.glob('release-*.json'))] for root in (self.authority,self.campaign)):
            raise AdmissionError('release journal missing or mirror mismatch')
        previous=0
        for i,name in enumerate(names,1):
            if name!=f'release-{i:02}.json':raise AdmissionError('release journal gap')
            record=self.mirrored(name)
            n=record['through_slot']
            if record['plan_hash']!=self.plan.digest() or record['previous_slot']!=previous or type(n) is not int or not previous<n<=6:
                raise AdmissionError('invalid release record')
            if i==1 and n!=1:raise AdmissionError('initial release must be slot 1')
            previous=n
        return previous

    def extend_release(self,through_slot,*,operator,reason):
        """Trusted operator only; never registered as a research capability."""
        self.load()
        if not operator.strip() or not reason.strip():raise AdmissionError('explicit operator and reason required')
        fd=lock(self.fence/'budget.lock',blocking=True)
        try:
            previous=self.released_through();self.slots()
            if type(through_slot) is not int or not previous<through_slot<=6:raise AdmissionError('release must increase within six-slot plan')
            count=len(list(self.fence.glob('release-*.json')))
            self.append_mirrored(f'release-{count+1:02}.json',self.release_record(previous,through_slot,operator,reason))
        finally:os.close(fd)

    def release_record(self,previous,n,operator,reason):
        return dict(plan_hash=self.plan.digest(),previous_slot=previous,through_slot=n,
                    operator=operator,reason=reason,code_commit=legacy.current_commit(),
                    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())

    def authorize(self,*,operator,reason):
        """Future trusted-operator API only. G4 CLI has no authorization command."""
        self.frozen_identity()
        if not operator.strip() or not reason.strip():raise AdmissionError('explicit operator and reason required')
        expected=self.expected()
        # Approved plan must be the versioned allowlisted file in the clean checkout.
        disk=SearchPlan.model_validate_json(read_bytes(PLAN_FILES[self.worker_id]))
        if disk!=self.plan:raise AdmissionError('plan not the committed worker plan')
        safe_dir(self.authority.parent);safe_dir(self.campaign.parent);safe_dir(self.fence.parent)
        # Exclusive persistent identity: deleting old ledgers cannot re-authorize.
        self.fence.mkdir(mode=0o700)
        self.authority.mkdir(mode=0o700);self.campaign.mkdir(mode=0o700)
        atomic_new(self.authority/'signing.key',secrets.token_bytes(32))
        self.append_mirrored('authorization.json',expected)
        self.append_mirrored('release-01.json',self.release_record(0,1,operator,reason))
        for p in (self.authority/'signing.key',self.authority/'authorization.json',self.campaign/'authorization.json'):p.chmod(0o400)
        return expected

    def load(self):
        self.frozen_identity()
        if not self.authority.exists() or not self.campaign.exists():raise AdmissionError('search campaign not authorized')
        self.secure(self.campaign);self.secure(self.authority)
        obj=self.mirrored('authorization.json')
        self.released_through()
        if obj!=self.expected():raise AdmissionError('plan/role/commit authorization mismatch')
        return obj

    def slots(self):
        primary=sorted(self.authority.glob('slot-*.json'))
        if [p.name for p in primary]!=[p.name for p in sorted(self.campaign.glob('slot-*.json'))]:
            raise AdmissionError('reservation mirror missing; review required')
        if [p.name for p in primary]!=[p.name for p in sorted(self.fence.glob('slot-*.json'))]:
            raise AdmissionError('persistent slot fence mismatch')
        records=[]
        for n,p in enumerate(primary,1):
            if p.name!=f'slot-{n}.json':raise AdmissionError('noncontiguous ledger')
            raw=read_bytes(p)
            if raw!=read_bytes(self.campaign/p.name):raise AdmissionError('reservation mirror mismatch')
            record=self.mirrored(p.name)
            if (record['slot']!=n or record['campaign_id']!=self.plan.campaign_id or record['plan_hash']!=self.plan.digest()):
                raise AdmissionError('reservation plan mismatch')
            records.append(record)
        if len(records)>self.plan.max_starts:raise AdmissionError('search ledger exceeds plan')
        return records

    def bind(self,number,raw):
        if number==1 and self.worker_id=='worker-02':
            p=Parameters.model_validate_json(raw)
            if p.model_dump()!={'learning_rate':.003,'weight_decay':.0001,'augmentation':'none'}:
                raise AdmissionError('preserve historical AI first proposal')
        return bind_request(self.plan,number,raw,legacy.current_commit(),self.worker_id,self.role)

    def reserve(self,raw):
        self.load()
        # Reject control fields before the lock and before any reservation.
        Parameters.model_validate_json(raw)
        fd=lock(self.fence/'budget.lock',blocking=True)
        try:
            auth=self.load();prior=self.slots();number=len(prior)+1
            if number>self.released_through():raise AdmissionError('slot not explicitly released')
            if number>self.plan.max_starts:raise AdmissionError('search start budget exhausted')
            if prior:
                previous=self.campaign/f'start-{number-1}'
                if not (previous/'result.json').is_file():raise AdmissionError('previous active/orphaned attempt')
                req=ExperimentConfig.model_validate_json(read_bytes(previous/'request.json'))
                result=Result.model_validate_json(read_bytes(previous/'result.json'));match_result(req,result)
                if hashlib.sha256(req.model_dump_json().encode()).hexdigest()!=prior[-1]['request_sha256']:
                    raise AdmissionError('prior request differs from reservation')
            req=self.bind(number,raw);trial=self.plan.trials[number-1]
            record={'campaign_id':self.plan.campaign_id,'task_id':self.plan.task_id,'role':self.role,
                    'worker_id':self.worker_id,'plan_hash':self.plan.digest(),'slot':number,'arm':trial.arm,
                    'seed':req.seed,'request_sha256':hashlib.sha256(req.model_dump_json().encode()).hexdigest(),
                    'parent_pid':os.getpid(),'code_commit':req.code_version,'evaluation_sha256':EVALUATION_HASH,
                    'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            self.append_mirrored(f'slot-{number}.json',record)
            return req,record
        finally:os.close(fd)

    def capability(self,record):
        fd=os.memfd_create('rs-search-dispatch',os.MFD_ALLOW_SEALING)
        os.write(fd,legacy.canonical(self.sign(record)));os.lseek(fd,0,os.SEEK_SET)
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL)
        return fd

    def claim(self,fd):
        required=fcntl.F_SEAL_WRITE|fcntl.F_SEAL_GROW|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_SEAL
        if fcntl.fcntl(fd,fcntl.F_GET_SEALS)&required!=required:raise AdmissionError('unsealed search capability')
        os.lseek(fd,0,os.SEEK_SET);receipt=self.verify(json.loads(os.read(fd,16384)))
        self.load();locked=lock(self.fence/'budget.lock',blocking=True)
        try:
            records=self.slots();n=receipt['slot']
            if n>self.released_through():raise AdmissionError('child slot not released')
            if not 1<=n<=self.plan.max_starts or n>len(records) or receipt!=records[n-1]:raise AdmissionError('unreserved search child')
            if receipt['parent_pid']!=os.getppid():raise AdmissionError('search parent mismatch')
            attempt=self.campaign/f'start-{n}'
            req=ExperimentConfig.model_validate_json(read_bytes(attempt/'request.json'))
            parameters={k:getattr(req.config,k) for k in ('learning_rate','weight_decay','augmentation')}
            expected=self.bind(n,json.dumps(parameters))
            if req!=expected or hashlib.sha256(req.model_dump_json().encode()).hexdigest()!=receipt['request_sha256']:
                raise AdmissionError('child request not in exact plan/role/seed')
            atomic_new(self.fence/f'claimed-{n}',b'one child forever per slot\n')
            atomic_new(self.authority/f'claimed-{n}',b'one search child before GPU\n')
            atomic_new(attempt/'child-started',b'authorized search child\n')
            return req,attempt,receipt
        finally:os.close(locked)
