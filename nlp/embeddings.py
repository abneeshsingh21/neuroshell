# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell NLP — Embedding Utilities  (Production Grade)
=========================================================
Provides a unified EmbeddingModel with:
  • sentence-transformers primary backend (MiniLM-L6)
  • Plain TF-IDF cosine fallback (zero external deps)
  • Thread-safe lazy initialisation
  • Similarity helpers used by SemanticSearch and the LLM client
"""

from __future__ import annotations

import logging
import math
import re
import threading
from typing import Optional

import numpy as np

_log = logging.getLogger("neuroshell.nlp.embeddings")

# ---------------------------------------------------------------------------
# Optional heavy backend
# ---------------------------------------------------------------------------

try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore[import-not-found]
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

# ---------------------------------------------------------------------------
# TF-IDF fallback (zero-dependency cosine similarity)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenise(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _tfidf_vector(tokens: list[str], vocab: dict[str, int]) -> np.ndarray:
    """Build a simple TF vector aligned to `vocab`."""
    vec = np.zeros(len(vocab), dtype=np.float32)
    for tok in tokens:
        if tok in vocab:
            vec[vocab[tok]] += 1.0
    # L2-normalise
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _build_vocab(corpus: list[list[str]]) -> dict[str, int]:
    vocab: dict[str, int] = {}
    for tokens in corpus:
        for tok in tokens:
            if tok not in vocab:
                vocab[tok] = len(vocab)
    return vocab


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Return cosine similarity in [-1, 1]. Returns 0 on zero vectors."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ---------------------------------------------------------------------------
# Main EmbeddingModel
# ---------------------------------------------------------------------------

class EmbeddingModel:
    """
    Unified embedding interface for NeuroShell.

    Priority:
        1. sentence-transformers/MiniLM (if installed) — 384-dim dense
        2. TF-IDF cosine fallback     (always available) — sparse

    Thread-safe: all public methods are protected by ``_lock``.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._st_model: Optional[object] = None
        self._lock = threading.Lock()
        self._loaded = False
        self._backend: str = "tfidf"         # "sentence-transformers" | "tfidf"

        # TF-IDF state (used when ST unavailable)
        self._tfidf_corpus_tokens: list[list[str]] = []
        self._tfidf_vocab: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Load the sentence-transformers backend (no-op if already loaded)."""
        with self._lock:
            if self._loaded:
                return True
            if _HAS_ST:
                try:
                    self._st_model = _SentenceTransformer(self._model_name)
                    self._backend = "sentence-transformers"
                    self._loaded = True
                    _log.info("EmbeddingModel loaded: %s (%s)", self._model_name, self._backend)
                    return True
                except Exception as exc:
                    _log.warning("Failed to load SentenceTransformer: %s — falling back to TF-IDF", exc)

            # TF-IDF fallback is always available
            self._backend = "tfidf"
            self._loaded = True
            _log.info("EmbeddingModel using TF-IDF fallback")
            return True

    # ------------------------------------------------------------------
    # Embed a single text
    # ------------------------------------------------------------------

    def embed(self, text: str) -> np.ndarray:
        """Return a normalised embedding vector for *text*."""
        if not self._loaded:
            self.initialize()

        with self._lock:
            if self._backend == "sentence-transformers" and self._st_model is not None:
                try:
                    result = self._st_model.encode(  # type: ignore[attr-defined]
                        [text],
                        show_progress_bar=False,
                        normalize_embeddings=True,
                    )
                    return result[0]
                except Exception:
                    pass  # fall through to TF-IDF

            # TF-IDF fallback
            tokens = _tokenise(text)
            vocab = dict(self._tfidf_vocab)
            # Add OOV tokens to vocab temporarily
            for tok in tokens:
                if tok not in vocab:
                    vocab[tok] = len(vocab)
            return _tfidf_vector(tokens, vocab)

    # ------------------------------------------------------------------
    # Batch embed
    # ------------------------------------------------------------------

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Return a 2D array (N, D) of normalised embeddings."""
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        if not self._loaded:
            self.initialize()

        with self._lock:
            if self._backend == "sentence-transformers" and self._st_model is not None:
                try:
                    return self._st_model.encode(  # type: ignore[attr-defined]
                        texts,
                        show_progress_bar=False,
                        normalize_embeddings=True,
                        batch_size=32,
                    )
                except Exception:
                    pass

            # TF-IDF batch fallback
            all_tokens = [_tokenise(t) for t in texts]
            # Build unified vocab from corpus + new texts
            combined = list(self._tfidf_corpus_tokens) + all_tokens
            vocab = _build_vocab(combined)
            return np.stack([_tfidf_vector(tok, vocab) for tok in all_tokens])

    # ------------------------------------------------------------------
    # Similarity helpers
    # ------------------------------------------------------------------

    def similarity(self, text_a: str, text_b: str) -> float:
        """Return pairwise cosine similarity between two texts (0–1)."""
        vecs = self.embed_batch([text_a, text_b])
        return cosine_similarity(vecs[0], vecs[1])

    def rank_by_similarity(
        self,
        query: str,
        candidates: list[str],
        top_k: int = 5,
        min_score: float = 0.2,
    ) -> list[tuple[str, float]]:
        """Return `top_k` most similar candidates with their scores."""
        if not candidates:
            return []
        texts = [query] + candidates
        vecs = self.embed_batch(texts)
        query_vec = vecs[0]
        results: list[tuple[str, float]] = []
        for i, text in enumerate(candidates):
            score = cosine_similarity(query_vec, vecs[i+1])
            if score >= min_score:
                results.append((text, round(score, 4)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # TF-IDF corpus management (fallback only)
    # ------------------------------------------------------------------

    def fit_tfidf(self, corpus: list[str]) -> None:
        """Pre-compute vocabulary from a corpus for the TF-IDF fallback."""
        all_tokens = [_tokenise(t) for t in corpus]
        with self._lock:
            self._tfidf_corpus_tokens = all_tokens
            self._tfidf_vocab = _build_vocab(all_tokens)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        return self._loaded

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def dimension(self) -> int:
        if self._backend == "sentence-transformers":
            return 384  # MiniLM-L6-v2
        return len(self._tfidf_vocab) or 512

    def __repr__(self) -> str:
        return f"EmbeddingModel(backend={self._backend!r}, loaded={self._loaded})"


# ---------------------------------------------------------------------------
# Module-level convenience singleton
# ---------------------------------------------------------------------------

_default_model: Optional[EmbeddingModel] = None
_singleton_lock = threading.Lock()


def get_default_model(model_name: str = "all-MiniLM-L6-v2") -> EmbeddingModel:
    """Return (and lazily initialise) the module-level singleton EmbeddingModel."""
    global _default_model
    with _singleton_lock:
        if _default_model is None:
            _default_model = EmbeddingModel(model_name)
            _default_model.initialize()
    return _default_model


def embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """Quick one-liner: embed a single text using the default model."""
    return get_default_model(model_name).embed(text)


def text_similarity(a: str, b: str) -> float:
    """Quick one-liner: cosine similarity between two texts."""
    return get_default_model().similarity(a, b)
