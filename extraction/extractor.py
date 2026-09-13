"""LLM-backed extraction (Phase 3 fast-follow) — provider-agnostic via LiteLLM.

Per ADR 0001, extraction is ours and must use an LLM with validation. Two backends
behind one protocol:

- ``NullExtractor`` — dependency-free default: returns an empty Extraction. Keeps CI
  and the pure-Python defaults free of any LLM call.
- ``LLMExtractor`` — optional (``.[llm]`` extra): typed entity/relation extraction
  through **LiteLLM**, so any provider works via the model string —
  ``anthropic/claude-opus-5``, ``openai/gpt-4o-mini``, ``ollama/llama3.1``, or a
  LiteLLM-proxy model with ``LLM_API_BASE``. We ask for JSON, send the Extraction
  JSON-schema in the prompt, then validate the response against the ``Extraction``
  pydantic model ourselves — a provider-portable equivalent of native structured
  outputs (the strictness of native schema enforcement varies by provider; our
  validation closes that gap).

Config:
  EXTRACTION_BACKEND = null | llm            (default null)
  EXTRACTION_MODEL   = <litellm model>       (default anthropic/claude-opus-5)
  LLM_API_BASE       = <url>                 (LiteLLM proxy / Ollama endpoint; optional)
  LLM_API_KEY        = <key>                 (optional; else provider env vars, e.g.
                                              ANTHROPIC_API_KEY / OPENAI_API_KEY)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Protocol

from fabric_client.models import Extraction

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "anthropic/claude-opus-5"

_SYSTEM = (
    "You extract a knowledge graph from enterprise text. Return ONLY typed entities and "
    "typed relations that are explicitly grounded in the text — never invent facts, and "
    "return empty lists if nothing is clearly stated.\n"
    "- Entities: canonical surface form + a concise type "
    "(e.g. Product, Organization, Policy, Cover, Term, Amount).\n"
    "- Relations: subject/predicate/object with a snake_case predicate "
    "(e.g. covers, offered_by, excludes, has_term). Subject and object should be "
    "entity names you also list under entities where possible.\n"
    "- Clean up entity spans: no page numbers, no font artifacts, no embedded newlines.\n"
    "Respond with a single JSON object only (no prose, no markdown fences) matching this "
    "JSON schema:\n{schema}"
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


def _parse_extraction(content: str) -> Extraction:
    """Validate model output against Extraction, tolerating fences/surrounding prose."""
    content = content.strip()
    try:
        return Extraction.model_validate_json(content)
    except Exception:
        pass
    # strip ```json fences / find the first {...} block
    fenced = re.sub(r"^```(?:json)?|```$", "", content, flags=re.MULTILINE).strip()
    try:
        return Extraction.model_validate_json(fenced)
    except Exception:
        pass
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if match:
        try:
            return Extraction.model_validate(json.loads(match.group(0)))
        except Exception:
            pass
    logger.warning("extraction: could not parse model output as Extraction JSON; returning empty.")
    return Extraction()


class LLMExtractor:
    """Provider-agnostic extractor over LiteLLM (Anthropic / OpenAI / Ollama / proxy)."""

    name = "llm"

    def __init__(
        self, model: str | None = None, max_tokens: int = 4096,
        api_base: str | None = None, api_key: str | None = None,
    ) -> None:
        import litellm  # optional dependency (.[llm])

        self._litellm = litellm
        self._model = model or os.getenv("EXTRACTION_MODEL", DEFAULT_MODEL)
        self._max_tokens = max_tokens
        self._api_base = api_base or os.getenv("LLM_API_BASE") or None
        self._api_key = api_key or os.getenv("LLM_API_KEY") or None

    @property
    def model(self) -> str | None:
        return self._model

    def extract(self, text: str, hint: str | None = None) -> Extraction:
        if not text.strip():
            return Extraction()
        schema = json.dumps(Extraction.model_json_schema())
        system = _SYSTEM.format(schema=schema)
        user = text if not hint else f"Domain: {hint}\n\nText:\n{text}"

        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self._max_tokens,
            "temperature": 0,
            # Widely supported (maps to Ollama `format: json`); we validate regardless.
            "response_format": {"type": "json_object"},
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key

        try:
            resp = self._litellm.completion(**kwargs)
        except Exception as exc:
            # Some providers/models reject response_format — retry once without it.
            if "response_format" in kwargs:
                kwargs.pop("response_format")
                try:
                    resp = self._litellm.completion(**kwargs)
                except Exception as exc2:
                    logger.warning("extraction LLM call failed (%s); returning empty.", exc2)
                    return Extraction()
            else:
                logger.warning("extraction LLM call failed (%s); returning empty.", exc)
                return Extraction()

        content = resp.choices[0].message.content or ""
        return _parse_extraction(content)


def build_extractor(kind: str | None) -> Extractor:
    """Factory from EXTRACTION_BACKEND. Falls back to NullExtractor if LiteLLM is absent."""
    choice = (kind or "null").strip().lower()
    # 'claude'/'anthropic'/'openai'/'ollama' all map to the one LiteLLM-backed extractor;
    # the provider is chosen by EXTRACTION_MODEL, not by a separate class.
    if choice in {"llm", "litellm", "claude", "anthropic", "openai", "ollama"}:
        try:
            return LLMExtractor()
        except Exception as exc:  # litellm missing / bad config at construction
            logger.warning("EXTRACTION_BACKEND=%s unavailable (%s); using NullExtractor.",
                           choice, exc)
            return NullExtractor()
    return NullExtractor()
