"""Local embeddings with bge-small on Apple Silicon (MPS), batched to keep memory flat."""
from __future__ import annotations

from functools import lru_cache

from common.config import settings
from common.device import free_memory, torch_device
from common.log import get_logger

log = get_logger("embedder")
# bge models expect this prefix on the QUERY side only (not on documents).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    dev = torch_device()
    name = settings()["knowledge_base"]["embed_model"]
    log.info("loading %s on %s", name, dev)
    return SentenceTransformer(name, device=dev), dev


def embed_documents(texts: list[str]) -> list[list[float]]:
    model, dev = _model()
    bs = settings()["knowledge_base"]["embed_batch_size"]
    out = []
    for i in range(0, len(texts), bs * 8):  # release GPU cache every 8 batches
        out.extend(model.encode(texts[i: i + bs * 8], batch_size=bs, normalize_embeddings=True,
                                show_progress_bar=False).tolist())
        free_memory(dev)
    return out


def embed_query(text: str) -> list[float]:
    model, _ = _model()
    return model.encode([QUERY_PREFIX + text], normalize_embeddings=True)[0].tolist()
