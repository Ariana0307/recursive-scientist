"""Read five training members only, after verifying the official archive."""
import hashlib
import pickle
from pathlib import PurePosixPath
import tarfile
import numpy as np

OFFICIAL_MD5 = 'c58f30108f718f92721af3b95e74349a'


def load_training(archive):
    if archive.is_symlink():
        raise ValueError('archive symlink rejected')
    md5, sha = hashlib.md5(), hashlib.sha256()
    # Keep the same descriptor from verification through reading; never reopen by name.
    with archive.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            md5.update(chunk)
            sha.update(chunk)
        if md5.hexdigest() != OFFICIAL_MD5:
            raise ValueError('official CIFAR archive MD5 mismatch')
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r:gz') as tar:
            names = set()
            for member in tar.getmembers():
                path = PurePosixPath(member.name)
                if (path.is_absolute() or '..' in path.parts or not path.parts
                        or path.parts[0] != 'cifar-10-batches-py'
                        or not (member.isfile() or member.isdir()) or member.name in names):
                    raise ValueError('unsafe archive member')
                names.add(member.name)
            images, labels = [], []
            for n in range(1, 6):
                member = tar.getmember(f'cifar-10-batches-py/data_batch_{n}')
                if not member.isfile():
                    raise ValueError('training member is not a regular file')
                with tar.extractfile(member) as batch:
                    record = pickle.load(batch, encoding='bytes')
                x = record[b'data']
                y = np.asarray(record[b'labels'], dtype=np.int64)
                if x.shape != (10000, 3072) or x.dtype != np.uint8 or y.shape != (10000,):
                    raise ValueError('invalid official training batch shape')
                if np.any(y < 0) or np.any(y > 9):
                    raise ValueError('invalid label range')
                images.append(x.reshape(10000, 3, 32, 32))
                labels.append(y)
    return np.concatenate(images), np.concatenate(labels), {
        'archive_md5': md5.hexdigest(), 'archive_sha256': sha.hexdigest(),
        'training_samples': 50000, 'official_test_read': False,
    }
