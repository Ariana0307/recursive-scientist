# G1 common environment

Use a dedicated Python 3.12 venv; never upgrade global packages. Contract checks do not require a GPU or CIFAR downloads.

```sh
python3.12 -m venv /your/private/location/rs-venv
/your/private/location/rs-venv/bin/python -m pip install -r requirements-test.txt
/your/private/location/rs-venv/bin/python -m pytest -q schemas/tests
# Worker 01 only, separate official CUDA wheel index:
/your/private/location/rs-venv/bin/python -m pip install -r requirements-torch.txt
```

Pinned direct dependencies: NumPy 2.2.6, Pydantic 2.11.7, RFC8785 0.1.4; torch 2.8.0+cu128. Do not install torchvision: prefer direct official CIFAR Python-batch reading. The CUDA wheel bundles its userspace runtime; do not modify system CUDA/drivers. Official wheel source: https://pytorch.org/get-started/previous-versions/ (2.8.0 / CUDA 12.8).

These are direct-dependency pins, not a full platform lock. Every worker must retain a private `pip freeze --all`, Python patch version, OS/architecture, torch version, torch.version.cuda, GPU/driver, deterministic settings, Git commit/dirty flag, config hash, split hash and verified archive SHA256. A hash-locked transitive environment will follow after both workers confirm compatibility. No claim of bit-identical results across different GPU hardware.

Data source: https://www.cs.toronto.edu/~kriz/cifar.html . Read only the verified official `cifar-10-python.tar.gz` training batches, in batch-number order and original row order. Verify the published archive checksum before deserialization, additionally record SHA256, and never unpickle untrusted inputs. Do not extract arbitrary archive paths; prefer reading the five named members directly. Do not read the test batch in G1. Control downloads no data.
