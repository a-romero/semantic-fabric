"""LLM-backed extraction (Phase 3 fast-follow).

Typed entity/relation extraction with validation, replacing semantica's noisy offline
default (ADR 0001). A no-op extractor is the default; the optional LLMExtractor works
across providers via LiteLLM (Anthropic / OpenAI / Ollama / proxy, by model string)
and validates output against the Extraction schema. Public surface:

    build_extractor(kind) -> Extractor
    Extractor.extract(text, hint) -> Extraction
"""

from .extractor import Extractor, LLMExtractor, NullExtractor, build_extractor

__all__ = ["Extractor", "NullExtractor", "LLMExtractor", "build_extractor"]
