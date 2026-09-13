"""Dense-PDF layout-parser wiring (raw pdf_b64 -> pages -> pipeline).

CI-safe: exercises the raw-bytes ingestion path with a STUB parser (no PDF library),
proving the wiring while the real PyMuPDF parser is validated on-env
(test_pdf_pymupdf_live). Also checks the null parser's actionable error.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from api import state
from api.main import app
from ingest.pdf_parser import NullPdfParser, PdfParserUnavailable, build_pdf_parser

client = TestClient(app)


class _StubParser:
    name = "stub"

    def parse(self, data: bytes, *, doc_id: str, title=None) -> dict:
        # Pretend to have parsed the bytes into one page of structured content.
        return {
            "doc_id": doc_id,
            "title": title or "Parsed Doc",
            "pages": [{
                "page": 1,
                "text": f"Parsed {len(data)} bytes of revenue prose.",
                "tables": [{"caption": "T", "rows": [["Q1", "3.1"]]}],
                "figures": [],
            }],
        }


def test_raw_pdf_bytes_are_parsed_then_ingested():
    state.set_pdf_parser(_StubParser())
    payload = {
        "kind": "pdf_batch",
        "payload": {"documents": [
            {"doc_id": "raw-doc", "title": "Raw Doc",
             "pdf_b64": base64.b64encode(b"%PDF-1.7 not really a pdf").decode()}
        ]},
    }
    r = client.post("/ingest", json=payload)
    assert r.status_code == 200 and r.json()["status"] == "done"

    # Parsed prose is searchable, and the generated summary tree was emitted.
    s = client.post("/search", json={"query": "revenue prose", "top_k": 5})
    assert any(u["type"] == "pdf_chunk" for u in s.json()["units"])
    assert state.get_kb().count("generated") >= 2


def test_null_parser_gives_actionable_error():
    state.set_pdf_parser(NullPdfParser())
    payload = {
        "kind": "pdf_batch",
        "payload": {"documents": [
            {"doc_id": "raw-doc", "pdf_b64": base64.b64encode(b"bytes").decode()}
        ]},
    }
    r = client.post("/ingest", json=payload)
    # PdfParserUnavailable subclasses ValueError -> reported as a failed job, not a 500.
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert ".[pdf]" in r.json()["detail"]

    with pytest.raises(PdfParserUnavailable):
        NullPdfParser().parse(b"x", doc_id="d")


def test_build_pdf_parser_defaults_to_null():
    assert isinstance(build_pdf_parser(None), NullPdfParser)
    # PyMuPDF not installed here -> falls back to null rather than raising.
    assert isinstance(build_pdf_parser("pymupdf"), NullPdfParser)


def test_pdf_pymupdf_live():
    """On-env: real PyMuPDF layout parsing of a PDF we synthesize with fitz itself."""
    fitz = pytest.importorskip("fitz")  # PyMuPDF
    from ingest.pdf_parser import PyMuPDFParser

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Group revenue grew in the third quarter.")
    data = doc.tobytes()
    doc.close()

    parsed = PyMuPDFParser().parse(data, doc_id="synth", title="Synth")
    assert parsed["doc_id"] == "synth" and parsed["pages"]
    assert "revenue" in parsed["pages"][0]["text"].lower()
