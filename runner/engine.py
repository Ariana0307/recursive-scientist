"""Child job: validate first, then initialize data/model/CUDA within parent deadline."""
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

from schemas.contracts import ExperimentConfig
from schemas.split import split_hash, split_indices
from runner.data import load_training
from runner.storage import atomic_new, digest, json_new, read_bytes

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / 'recursive-scientist-local'


def check_environment():
    required = {'numpy': '2.2.6', 'pydantic': '2.11.7', 'rfc8785': '0.1.4', 'torch': '2.8.0+cu128'}
    if sys.version_info[:2] != (3, 12) or sys.prefix == sys.base_prefix or not sys.flags.isolated:
        raise RuntimeError('independent Python 3.12 with -I required')
    if any(not p.startswith(sys.prefix + os.sep) for p in sys.path if 'site-packages' in p):
        raise RuntimeError('external site-packages detected')
    for name, version in required.items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError('contract dependency version mismatch: ' + name)
    cfg = (Path(sys.prefix) / 'pyvenv.cfg').read_text().lower()
    if 'include-system-site-packages = false' not in cfg:
        raise RuntimeError('system-site-packages must be disabled')
    return {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}


def check_checkout(request):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True)
    if dirty or head != request.code_version:
        raise RuntimeError('request requires the exact clean runner commit')
    if request.status != 'approved':
        raise ValueError('proposed request is not authorized')


def preflight():
    packages = check_environment()
    images, labels, data = load_training(PRIVATE / 'data/cifar-10-python.tar.gz')
    train, validation = split_indices()
    if images.shape != (50000, 3, 32, 32) or len(labels) != 50000:
        raise ValueError('dataset dimensions differ')
    import torch
    return {'status': 'passed', 'python': platform.python_version(), 'packages': packages,
            'data': data, 'split_indices_hash': split_hash(), 'train_count': len(train),
            'validation_count': len(validation), 'cuda_initialized': torch.cuda.is_initialized()}


def child(attempt):
    """Only supervisor creates these fixed private paths; context is never agent input."""
    request = ExperimentConfig.model_validate_json(read_bytes(attempt.parent / 'request.json'))
    check_checkout(request)
    packages = check_environment()
    context = json.loads(read_bytes(attempt / 'context.json'))
    if context['parent_pid'] != os.getppid():
        raise RuntimeError('child requires its admitting supervisor')
    if context['request_sha256'] != digest(request.model_dump_json().encode()):
        raise RuntimeError('child request digest differs')
    slot = context['quota']['slot']
    reservation = json.loads(read_bytes(attempt.parent.parent / '.g1-quota' / f'slot-{slot}.json'))
    if reservation != context['quota']:
        raise RuntimeError('child reservation differs')
    atomic_new(attempt / 'child-started', b'one child process per quota reservation\n')
    train_job(request, packages, attempt, context)


def train_job(request, packages, attempt, context):
    # Called only after either the legacy guard or G3 parent+child authorization.
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    import numpy as np
    import torch
    from runner.model import small_cnn, preprocess
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    random.seed(request.seed)
    np.random.seed(request.seed)
    torch.manual_seed(request.seed)
    torch.cuda.manual_seed_all(request.seed)
    images, labels, data = load_training(PRIVATE / 'data/cifar-10-python.tar.gz')
    train, validation = split_indices()
    json_new(attempt / 'split-indices.json', {'train': train, 'validation': validation})
    json_new(attempt / 'data.json', data)
    # Record complete CPU-side provenance before CUDA; device evidence follows init.
    json_new(attempt / 'provenance.json', {
        'code_commit': request.code_version, 'working_tree_dirty': False,
        'python': platform.python_version(), 'os': platform.system(),
        'os_release': platform.release(), 'architecture': platform.machine(),
        'packages': packages, 'torch': torch.__version__, 'torch_cuda': torch.version.cuda,
        'config_hash': request.config_hash, 'split_indices_hash': split_hash(),
        'seed': request.seed, 'data': data, 'system_site_packages': False,
        'deterministic_algorithms': True, 'cudnn_benchmark': False, 'tf32': False,
        'cublas_workspace_config': ':4096:8', 'num_workers': 0,
        'rng': 'Python random.seed; NumPy legacy seed; torch.manual_seed and cuda.manual_seed_all; dedicated CPU torch.Generator(seed) shared sequentially by randperm shuffle and per-image randint(0,9,(2,))/rand flip; no DataLoader worker RNG',
        'mode': context['mode'], 'subset_is_benchmark': False,
        'campaign_id': context.get('campaign_id'),
        'evaluation_sha256': context.get('evaluation_sha256'),
    })
    freeze = '\n'.join(f'{k}=={v}' for k, v in sorted(packages.items())) + '\n'
    atomic_new(attempt / 'environment-freeze.txt', freeze.encode())
    x = torch.from_numpy(images)
    y = torch.from_numpy(labels)
    generator = torch.Generator(device='cpu').manual_seed(request.seed)
    device = torch.device('cuda')
    model = small_cnn().to(device)
    driver = subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'], text=True).strip().splitlines()[0]
    json_new(attempt / 'device.json', {'actual_device': 'cuda', 'gpu': torch.cuda.get_device_name(0),
                                     'driver': driver, 'capability': list(torch.cuda.get_device_capability(0))})
    optimizer = torch.optim.Adam(model.parameters(), lr=request.config.learning_rate,
                                 weight_decay=request.config.weight_decay, betas=(0.9, 0.999), eps=1e-8)
    criterion = torch.nn.CrossEntropyLoss(reduction='mean')
    smoke = context['mode'] == 'smoke'
    train_ids = torch.tensor(train[:128] if smoke else train, dtype=torch.int64)
    val_ids = torch.tensor(validation[:64] if smoke else validation, dtype=torch.int64)
    start = time.monotonic()
    for epoch in range(1 if smoke else request.config.epochs):
        model.train()
        order = train_ids[torch.randperm(len(train_ids), generator=generator)]
        for idx in order.split(request.config.batch_size):
            batch = preprocess(x[idx], request.config.augmentation, generator).to(device)
            target = y[idx].to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(batch), target)
            if not torch.isfinite(loss):
                raise RuntimeError('nonfinite training loss')
            loss.backward()
            optimizer.step()
        print(json.dumps({'epoch': epoch + 1, 'training_samples': len(train_ids)}), flush=True)
    from runner.evaluate import evaluate
    predictions = [] if context.get('campaign_id') else None
    correct, loss_sum, count = evaluate(model, x, y, val_ids, request.config.batch_size,
                                       device, generator, criterion, predictions)
    if predictions is not None:
        json_new(attempt / 'predictions.json', {'columns': ['train_index', 'target', 'predicted'],
                                               'rows': predictions, 'split': 'validation-only'})
    torch.cuda.synchronize()
    json_new(attempt / 'execution.json', {'train_count': len(train_ids), 'validation_count': count,
                                         'epochs': 1 if smoke else request.config.epochs,
                                         'training_validation_seconds': time.monotonic() - start,
                                         'diagnostic_only': smoke})
    if smoke:
        # v1 forbids subset success or partial metrics. No diagnostic accuracy is emitted.
        json_new(attempt / 'outcome.json', {'status': 'cancelled', 'metrics': {'accuracy': None, 'loss': None},
                 'error': {'kind': 'cancelled', 'message': 'Operator diagnostic smoke completed on 128 train/64 validation samples; full experiment intentionally not run.'}})
    else:
        if len(train_ids) != 45000 or count != 5000:
            raise RuntimeError('full split required for success')
        if context.get('save_state_dict'):
            from runner.model_artifact import stage
            stage(model, attempt, request, context['evaluation_sha256'])
        json_new(attempt / 'outcome.json', {'status': 'succeeded', 'metrics': {'accuracy': correct / count, 'loss': loss_sum / count}, 'error': None})
