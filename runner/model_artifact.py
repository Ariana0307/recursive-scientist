"""Tensor-only state_dict artifacts; a matching successful Result is the commit marker."""
import hashlib
import io
import json
import os
from pathlib import Path
from runner.storage import atomic_new, json_new, read_bytes, safe_dir, AdmissionError
from schemas.contracts import ExperimentConfig, Result, match_result


def stage(model, run, request, evaluation_sha256):
    import torch
    run=Path(run);safe_dir(run)
    pending=run/'.model-pending'
    pending.mkdir(mode=0o700)
    # Only tensors, no model object, optimizer, RNG objects or callable pickle targets.
    state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
    if not all(type(k) is str and isinstance(v,torch.Tensor) for k,v in state.items()):
        raise ValueError('tensor-only state_dict required')
    buffer=io.BytesIO();torch.save(state,buffer);data=buffer.getvalue()
    atomic_new(pending/'state_dict.pt',data)
    metadata={'format':'torch-state-dict-tensors-v1','filename':'state_dict.pt','sha256':hashlib.sha256(data).hexdigest(),
              'bytes':len(data),'seed':request.seed,'config':request.config.model_dump(mode='json'),
              'config_hash':request.config_hash,'training_commit':request.code_version,
              'evaluation_sha256':evaluation_sha256,'experiment_id':request.experiment_id,
              'requires_matching_success_result':True}
    json_new(pending/'artifact.json',metadata)
    return metadata


def publish_pending(run, request, evaluation_sha256):
    run=Path(run);pending=run/'.model-pending';final=run/'model-artifact'
    safe_dir(run)
    if pending.is_symlink() or final.exists() or final.is_symlink():
        raise AdmissionError('artifact path conflict')
    data=read_bytes(pending/'state_dict.pt');m=json.loads(read_bytes(pending/'artifact.json'))
    if (m['sha256']!=hashlib.sha256(data).hexdigest() or m['bytes']!=len(data)
            or m['seed']!=request.seed or m['config_hash']!=request.config_hash
            or m['config']!=request.config.model_dump(mode='json') or m['training_commit']!=request.code_version
            or m['experiment_id']!=request.experiment_id or m['evaluation_sha256']!=evaluation_sha256
            or m['filename']!='state_dict.pt' or m['requires_matching_success_result'] is not True):
        raise AdmissionError('artifact provenance/hash mismatch')
    # The private run has one admitting parent; rename publishes the complete directory.
    os.rename(pending,final)
    fd=os.open(run,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return m


def load_success(run, request, evaluation_sha256):
    """Trusted resolved run identity only; never an external/model-supplied weights path."""
    import torch
    run=Path(run)
    result=Result.model_validate_json(read_bytes(run/'result.json'));match_result(request,result)
    if result.status!='succeeded':raise AdmissionError('no successful artifact for failed/cancelled run')
    artifact=run/'model-artifact'
    if artifact.is_symlink():raise AdmissionError('artifact symlink')
    metadata=json.loads(read_bytes(artifact/'artifact.json'));data=read_bytes(artifact/'state_dict.pt')
    expected={'seed':request.seed,'config_hash':request.config_hash,'training_commit':request.code_version,
              'evaluation_sha256':evaluation_sha256,'experiment_id':request.experiment_id,
              'config':request.config.model_dump(mode='json'),'filename':'state_dict.pt',
              'format':'torch-state-dict-tensors-v1','requires_matching_success_result':True}
    if any(metadata.get(k)!=v for k,v in expected.items()) or metadata['sha256']!=hashlib.sha256(data).hexdigest() or metadata['bytes']!=len(data):
        raise AdmissionError('successful artifact identity/hash mismatch')
    state=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True)
    if not isinstance(state,dict) or not all(type(k) is str and isinstance(v,torch.Tensor) for k,v in state.items()):
        raise AdmissionError('not a tensor state_dict')
    return state,metadata
