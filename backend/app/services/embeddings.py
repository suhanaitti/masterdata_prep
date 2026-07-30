"""
embeddings.py
-------------
Local embedding generation (sentence-transformers, no API calls/rate limits) and
numpy-based cosine similarity search, used to add a semantic-search signal to field
mapping ALONGSIDE the existing BM25 keyword retrieval in retrieval.py - not instead
of it (the two rankings are combined via reciprocal_rank_fusion(), see
field_mapping_engine.py). Ported from the sibling Header_Mapping project's
embeddings.py, trimmed to this project's simpler master_fields shape
(column_name + ai_description only - no data_element/section columns here).
"""
import re
import threading

import numpy as np

_MODEL = None
_MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, small, fast, good general-purpose quality
_model_lock = threading.Lock()
_warm_up_started = False
_warm_up_started_lock = threading.Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _model_lock:
            if _MODEL is None:
                from sentence_transformers import SentenceTransformer
                _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def warm_model_async() -> None:
    """Starts loading the embedding model in a background thread at server startup,
    instead of paying the ~30-60s one-time load cost on whatever request happens to
    call embed_texts() first. Safe to call repeatedly - _MODEL is a process-wide
    singleton, so only the first call across the server's lifetime loads anything."""
    global _warm_up_started
    with _warm_up_started_lock:
        if _warm_up_started:
            return
        _warm_up_started = True
    threading.Thread(target=_get_model, daemon=True).start()


def embed_texts(texts: list) -> list:
    """Returns a list of embedding vectors (each a list of floats), one per input text."""
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(list(texts), show_progress_bar=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def embed_text(text: str) -> list:
    return embed_texts([text])[0]


def humanize_identifier(token: str) -> str:
    """Splits a CamelCase/snake_case/dotted technical identifier into space-separated
    words, so an opaque code carries real meaning to the embedding model, e.g.
    "CustNo" -> "Cust No", "customer_number" -> "customer number"."""
    if not token:
        return ""
    t = re.sub(r"[_./\-]+", " ", token.strip())
    t = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", t)
    t = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def field_embedding_text(column_name: str, ai_description: str = None) -> str:
    """What actually gets embedded for a master_fields row. column_name is humanized
    (CamelCase/snake_case split into words) so a terse code still embeds with its real
    meaning; ai_description (already a full sentence from metadata_generator.py) is
    appended when present."""
    name_human = humanize_identifier(column_name) or (column_name or "")
    desc = (ai_description or "").strip()
    return f"{name_human}: {desc}" if desc else name_human


def top_k_candidates(query_vectors: np.ndarray, candidate_vectors: np.ndarray, k: int) -> np.ndarray:
    """
    query_vectors: (num_queries, dim)
    candidate_vectors: (num_candidates, dim)
    Returns: (num_queries, k) array of candidate indices, best match first.
    """
    q_norm = query_vectors / np.linalg.norm(query_vectors, axis=1, keepdims=True).clip(min=1e-10)
    c_norm = candidate_vectors / np.linalg.norm(candidate_vectors, axis=1, keepdims=True).clip(min=1e-10)
    similarity = q_norm @ c_norm.T

    k = min(k, candidate_vectors.shape[0])
    top_idx = np.argpartition(-similarity, k - 1, axis=1)[:, :k]
    row_idx = np.arange(similarity.shape[0])[:, None]
    order = np.argsort(-similarity[row_idx, top_idx], axis=1)
    return top_idx[row_idx, order]


def top_n_by_cosine(query_vector: list, candidate_ids: list, candidate_vectors: list, n: int) -> list:
    """Convenience single-query wrapper used by field_mapping_engine.py: returns up to
    n candidate_ids, best cosine-similarity match first."""
    if not candidate_ids:
        return []
    q = np.array([query_vector])
    c = np.array(candidate_vectors)
    idx = top_k_candidates(q, c, n)[0]
    return [candidate_ids[i] for i in idx]
