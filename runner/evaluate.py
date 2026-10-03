"""Frozen scoring; extracted unchanged from G1, with optional prediction evidence."""
import torch
from runner.model import preprocess


def evaluate(model, x, y, val_ids, batch_size, device, generator, criterion, evidence=None):
    model.eval()
    correct, loss_sum, count = 0, 0.0, 0
    with torch.no_grad():
        for idx in val_ids.split(batch_size):
            target = y[idx].to(device)
            logits = model(preprocess(x[idx], 'none', generator).to(device))
            loss = criterion(logits, target)
            if not torch.isfinite(loss):
                raise RuntimeError('nonfinite validation loss')
            loss_sum += loss.item() * len(idx)
            correct += (logits.argmax(1) == target).sum().item()
            count += len(idx)
            if evidence is not None:
                evidence.extend(zip(idx.tolist(), target.tolist(), logits.argmax(1).tolist()))
    return correct, loss_sum, count
