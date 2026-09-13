"""Phase 3 fast-follow: LLM-backed extraction tests (provider-agnostic).

The default backend (NullExtractor) is dependency-free and used by CI. The LLMExtractor
(LiteLLM) is exercised only when litellm is installed AND EXTRACTION_LIVE is set (a
credential for the chosen EXTRACTION_MODEL's provider must be present) — otherwise
skipped, so CI stays offline and free. The JSON-parsing/validation path is tested
offline without any network call.
"""

import os

import pytest
from fabric_client.models import Extraction
from fastapi.testclient import TestClient

from api.main import app
from extraction.extractor import NullExtractor, _parse_extraction, build_extractor

client = TestClient(app)


def test_null_extractor_returns_empty():
    ex = NullExtractor()
    out = ex.extract("Aviva offers a Survivor Trust for life cover.")
    assert isinstance(out, Extraction)
    assert out.entities == [] and out.relations == []


def test_build_extractor_defaults_to_null():
    assert build_extractor(None).name == "null"
    # Any provider alias maps to the one LiteLLM extractor; falls back to null if litellm absent.
    for alias in ("llm", "anthropic", "openai", "ollama"):
        assert build_extractor(alias).name in {"llm", "null"}


def test_parse_extraction_validates_against_schema():
    # plain JSON
    out = _parse_extraction(
        '{"entities":[{"name":"ISA","type":"Product"}],'
        '"relations":[{"subject":"ISA","predicate":"is_a","object":"savings account",'
        '"confidence":0.9}]}'
    )
    assert [e.name for e in out.entities] == ["ISA"]
    assert out.relations[0].predicate == "is_a"


def test_parse_extraction_tolerates_fences_and_prose():
    messy = 'Here is the graph:\n```json\n{"entities":[{"name":"Aviva","type":"Organization"}],' \
            '"relations":[]}\n```'
    out = _parse_extraction(messy)
    assert out.entities[0].type == "Organization"


def test_parse_extraction_bad_output_returns_empty():
    assert _parse_extraction("sorry, I cannot help with that").entities == []


def test_extract_endpoint_shape():
    r = client.post("/extract", json={"text": "An ISA is a tax-efficient savings account.",
                                      "hint": "UK insurance & pensions"})
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "null"          # default backend in CI
    assert body["entities"] == [] and body["relations"] == []


@pytest.mark.skipif(
    "EXTRACTION_LIVE" not in os.environ,
    reason="set EXTRACTION_LIVE=1 (with litellm + provider creds) to run live extraction",
)
def test_llm_extractor_live():
    pytest.importorskip("litellm")
    from extraction.extractor import LLMExtractor

    ex = LLMExtractor()  # provider chosen by EXTRACTION_MODEL
    out = ex.extract(
        "Aviva offers the Enhanced Pension Annuity, which pays a guaranteed income for life.",
        hint="UK insurance & pensions",
    )
    assert isinstance(out, Extraction)
    assert out.entities, "expected at least one extracted entity"
