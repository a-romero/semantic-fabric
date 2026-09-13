"""LLM-backed extraction (Phase 3 fast-follow).

Typed entity/relation extraction with validation, replacing semantica's noisy offline
default (ADR 0001). A no-op extractor is the default; the optional Claude backend uses
structured outputs so every result is a schema-validated Extraction. Public surface:

    build_extractor(kind) -> Extractor
    Extractor.extract(text, hint) -> Extraction
"""

from .extractor import ClaudeExtractor, Extractor, NullExtractor, build_extractor

__all__ = ["Extractor", "NullExtractor", "ClaudeExtractor", "build_extractor"]
