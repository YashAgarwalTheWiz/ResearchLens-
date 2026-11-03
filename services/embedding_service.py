"""Local embeddings with sentence-transformers (no API key, no internet after the first download).
The model (~90 MB) downloads once on first use and is cached on your machine."""
from typing import List

from config import EMBEDDING_MODEL

_model = None


def _get_model():
    global _model
    if _model is None:                       # load lazily: only when first needed, then reuse
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _model


def get_embeddings(texts: List[str], input_type: str = 'search_document') -> List[List[float]]:
    # input_type is kept so existing callers don't break; this model treats queries and documents the same
    if not texts:
        return []
    vectors = _get_model().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()