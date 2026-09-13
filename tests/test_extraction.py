"""Phase 3 fast-follow: LLM-backed extraction tests.

The default backend (NullExtractor) is dependency-free and used by CI. The Claude
backend is exercised only when the .[llm] extra is installed AND an API credential is
present — otherwise skipped, so CI stays offline and free.
"""

import os

import pytest
from fabric_client.models import Extraction
from fastapi.testclient import TestClient

from api.main import app
from extraction.extractor import NullExtractor, build_extractor

client = TestClient(app)


def test_null_extractor_returns_empty():
    ex = NullExtractor()
    out = ex.extract("Aviva offers a Survivor Trust for life cover.")
    assert isinstance(out, Extraction)
    assert out.entities == [] and out.relations == []


def test_build_extractor_defaults_to_null():
    assert build_extractor(None).name == "null"
    # Asking for claude without the SDK/creds falls back safely to null.
    assert build_extractor("claude").name in {"claude", "null"}


def test_extract_endpoint_shape():
    r = client.post("/extract", json={"text": "An ISA is a tax-efficient savings account.",
                                      "hint": "UK insurance & pensions"})
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "null"          # default backend in CI
    assert body["entities"] == [] and body["relations"] == []


@pytest.mark.skipif(
    "ANTHROPIC_API_KEY" not in os.environ, reason="no Anthropic credential; live extraction skipped"
)
def test_claude_extractor_live():
    pytest.importorskip("anthropic")
    from extraction.extractor import ClaudeExtractor

    ex = ClaudeExtractor()
    out = ex.extract(
        "Aviva offers the Enhanced Pension Annuity, which pays a guaranteed income for life.",
        hint="UK insurance & pensions",
    )
    assert isinstance(out, Extraction)
    # A capable model should find at least the product entity.
    assert out.entities, "expected at least one extracted entity"
