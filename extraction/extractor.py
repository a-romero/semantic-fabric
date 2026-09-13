"""LLM-backed extraction (Phase 3 fast-follow).

Per ADR 0001, extraction is ours (semantica's offline default was too noisy) and must
use an LLM with validation. Two backends behind one protocol:

- ``NullExtractor`` — dependency-free default: returns an empty Extraction. Keeps CI
  and the pure-Python defaults free of any LLM call.
- ``ClaudeExtractor`` — optional (``.[llm]`` extra): extracts typed entities +
  relations with the Anthropic SDK via structured outputs
  (``client.messages.parse(output_format=Extraction)``), so every result is a
  schema-validated ``Extraction`` — validation is inherent, not bolted on.

Selected by ``EXTRACTION_BACKEND`` (``null`` default, ``claude`` in deployment);
model via ``EXTRACTION_MODEL`` (default ``claude-opus-5``).
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

from fabric_client.models import Extraction

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

_SYSTEM = (
    "You extract a knowledge graph from enterprise text. Return ONLY typed entities and "
    "typed relations that are explicitly grounded in the text — never invent facts, and "
    "return empty lists if nothing is clearly stated.\n"
    "- Entities: canonical surface form + a concise type "
    "(e.g. Product, Organization, Policy, Cover, Term, Amount).\n"
    "- Relations: subject/predicate/object with a snake_case predicate "
    "(e.g. covers, offered_by, excludes, has_term). Subject and object should be "
    "entity names you also list under entities where possible.\n"
    "- Clean up entity spans: no page numbers, no font artifacts, no embedded newlines."
)


class Extractor(Protocol):
    def extract(self, text: str, hint: str | None = None) -> Extraction: ...

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str | None: ...


class NullExtractor:
    """No-op extractor. The default so ingestion/CI never require an LLM."""

    name = "null"
    model = None

    def extract(self, text: str, hint: str | None = None) -> Extraction:
        return Extraction()


class ClaudeExtractor:
    """Typed entity/relation extraction via the Anthropic SDK (structured outputs)."""

    name = "claude"

    def __init__(self, model: str | None = None, max_tokens: int = 4096) -> None:
        import anthropic  # optional dependency

        self._client = anthropic.Anthropic()  # resolves creds from env / ant profile
        self._model = model or os.getenv("EXTRACTION_MODEL", DEFAULT_MODEL)
        self._max_tokens = max_tokens

    @property
    def model(self) -> str | None:
        return self._model

    def extract(self, text: str, hint: str | None = None) -> Extraction:
        if not text.strip():
            return Extraction()
        user = text if not hint else f"Domain: {hint}\n\nText:\n{text}"
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_format=Extraction,
        )
        # parsed_output is a schema-validated Extraction (structured outputs).
        return response.parsed_output or Extraction()


def build_extractor(kind: str | None) -> Extractor:
    """Factory from EXTRACTION_BACKEND. Falls back to NullExtractor if the LLM SDK is absent."""
    choice = (kind or "null").strip().lower()
    if choice == "claude":
        try:
            return ClaudeExtractor()
        except Exception as exc:  # anthropic missing / no creds at construction
            logger.warning("EXTRACTION_BACKEND=claude unavailable (%s); using NullExtractor.", exc)
            return NullExtractor()
    return NullExtractor()
