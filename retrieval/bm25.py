"""Minimal, dependency-free BM25 over an in-memory corpus.

Keeps the base install light. Swappable for a service-backed lexical index later; the
RetrievalIndex only relies on ``add`` and ``search``.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._ids: list[str] = []
        self._tokens: list[list[str]] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avg_len = 0.0

    def add(self, doc_id: str, text: str) -> None:
        toks = tokenize(text)
        self._ids.append(doc_id)
        self._tokens.append(toks)
        tf = Counter(toks)
        self._tf.append(tf)
        for term in tf:
            self._df[term] += 1
        total = sum(len(t) for t in self._tokens)
        self._avg_len = total / len(self._tokens) if self._tokens else 0.0

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if not self._ids:
            return []
        q_terms = tokenize(query)
        n = len(self._ids)
        scores: list[tuple[str, float]] = []
        for idx, doc_id in enumerate(self._ids):
            tf = self._tf[idx]
            dl = len(self._tokens[idx])
            score = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                df = self._df[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self._avg_len or 1))
                score += idf * (freq * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((doc_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
