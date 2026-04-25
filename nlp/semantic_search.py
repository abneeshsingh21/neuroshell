# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
"""
NeuroShell Semantic Search
Embedding-based command history search using sentence-transformers.
"""

import time
import numpy as np
from typing import Optional
from dataclasses import dataclass, field

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


@dataclass
class SearchResult:
    """A single search result."""
    command: str
    similarity: float
    context: str = ""
    timestamp: float = 0


class SemanticSearch:
    """Embedding-based command search using MiniLM."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._embeddings: Optional[np.ndarray] = None
        self._commands: list[dict] = []  # {command, context, timestamp}
        self._loaded = False

    def initialize(self) -> bool:
        """Load the sentence transformer model."""
        if not HAS_SENTENCE_TRANSFORMERS:
            return False

        try:
            self._model = SentenceTransformer(self._model_name)
            self._loaded = True
            return True
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        return self._loaded and self._model is not None

    def index_commands(self, commands: list[dict]):
        """
        Build embedding index from command history.

        Args:
            commands: List of dicts with 'command', 'context', 'timestamp'
        """
        if not self.is_available or not commands:
            return

        self._commands = commands
        texts = []
        for cmd in commands:
            # Combine command with context for richer embeddings
            text = cmd.get("command", "")
            ctx = cmd.get("context", "")
            if ctx:
                text = f"{text} ({ctx})"
            texts.append(text)

        try:
            self._embeddings = self._model.encode(
                texts,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
        except Exception:
            self._embeddings = None

    def add_command(self, command: str, context: str = "", timestamp: float = 0):
        """Add a single command to the index."""
        if not self.is_available:
            return

        entry = {"command": command, "context": context, "timestamp": timestamp or time.time()}
        self._commands.append(entry)

        text = f"{command} ({context})" if context else command

        try:
            new_embedding = self._model.encode(
                [text],
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            if self._embeddings is not None:
                self._embeddings = np.vstack([self._embeddings, new_embedding])
            else:
                self._embeddings = new_embedding
        except Exception:
            pass

    def search(self, query: str, top_k: int = 5, min_similarity: float = 0.3) -> list[SearchResult]:
        """Search for semantically similar commands."""
        if not self.is_available or self._embeddings is None or len(self._commands) == 0:
            return []

        try:
            # Encode query
            query_embedding = self._model.encode(
                [query],
                show_progress_bar=False,
                normalize_embeddings=True,
            )

            # Cosine similarity (embeddings are normalized, so dot product = cosine)
            similarities = np.dot(self._embeddings, query_embedding.T).flatten()

            # Get top-k results above threshold
            top_indices = np.argsort(similarities)[::-1][:top_k]

            results = []
            for idx in top_indices:
                sim = float(similarities[idx])
                if sim < min_similarity:
                    break
                cmd = self._commands[idx]
                results.append(SearchResult(
                    command=cmd["command"],
                    similarity=round(sim, 3),
                    context=cmd.get("context", ""),
                    timestamp=cmd.get("timestamp", 0),
                ))

            return results
        except Exception:
            return []

    def find_similar(self, command: str, top_k: int = 3) -> list[SearchResult]:
        """Find commands similar to the given one."""
        return self.search(command, top_k=top_k, min_similarity=0.5)

    def get_stats(self) -> dict:
        """Get search index statistics."""
        return {
            "model_loaded": self._loaded,
            "model_name": self._model_name,
            "indexed_commands": len(self._commands),
            "embedding_dim": self._embeddings.shape[1] if self._embeddings is not None else 0,
        }
