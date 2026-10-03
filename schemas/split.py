"""Deterministic CIFAR training-index split; never downloads or opens data."""
from functools import lru_cache
import hashlib
import numpy as np
import rfc8785

SPLIT_SEED = 20261003
SPLIT_ID = "cifar10-train45000-val5000-pcg64-v1"

@lru_cache(maxsize=1)
def split_indices() -> tuple[tuple[int, ...], tuple[int, ...]]:
    permutation = np.random.Generator(np.random.PCG64(SPLIT_SEED)).permutation(50000)
    validation = tuple(sorted(int(i) for i in permutation[:5000]))
    train = tuple(sorted(int(i) for i in permutation[5000:]))
    return train, validation

@lru_cache(maxsize=1)
def split_hash() -> str:
    train, validation = split_indices()
    digest = hashlib.sha256(rfc8785.dumps({"train": list(train), "validation": list(validation)})).hexdigest()
    if digest != "48a8983fa5fdf95d137855c818b7bc716c476396dbe5b274eec41982b27e815e":
        raise RuntimeError("split differs from frozen G1 manifest; check the pinned environment")
    return digest
