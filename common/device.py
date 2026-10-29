"""Pick the fastest torch device. On an M-series Mac this is 'mps'."""
from __future__ import annotations

import os


def torch_device() -> str:
    forced = os.getenv("EMBED_DEVICE", "").strip()
    if forced:
        return forced
    try:
        import torch

        if torch.backends.mps.is_available():
            # Fall back to CPU for any op MPS does not support, instead of crashing.
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def free_memory(device: str) -> None:
    """Release cached GPU memory between batches (keeps the 24GB machine responsive)."""
    try:
        import gc

        import torch

        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()
        elif device == "cuda":
            torch.cuda.empty_cache()
    except Exception:
        pass
