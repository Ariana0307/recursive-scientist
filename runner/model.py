"""Contract-fixed architecture and explicit CPU RNG image preprocessing."""
import torch
from torch import nn
from torch.nn import functional as F


def small_cnn():
    return nn.Sequential(nn.Conv2d(3, 32, 3, padding=1, bias=True), nn.ReLU(), nn.MaxPool2d(2),
                         nn.Conv2d(32, 64, 3, padding=1, bias=True), nn.ReLU(), nn.MaxPool2d(2),
                         nn.Flatten(), nn.Linear(64 * 8 * 8, 128, bias=True), nn.ReLU(),
                         nn.Linear(128, 10, bias=True))


def preprocess(images, augmentation, generator):
    if augmentation == 'basic':
        padded = F.pad(images, (4, 4, 4, 4), value=0)
        augmented = []
        for item in padded:
            top, left = torch.randint(0, 9, (2,), generator=generator).tolist()
            crop = item[:, top:top + 32, left:left + 32]
            if torch.rand((), generator=generator).item() < 0.5:
                crop = crop.flip(-1)
            augmented.append(crop)
        images = torch.stack(augmented)
    return (images.to(torch.float32) / 255.0 - 0.5) / 0.5
