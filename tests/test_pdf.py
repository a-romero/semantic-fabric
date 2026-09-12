"""Phase 2 dense-PDF ingestion tests (pre-parsed payload path).

Exercises the full downstream — prose->pdf_chunk, tables->table_row,
figures->object store + chart_caption, and the generated/ summary tree — without a
PDF library or vision model.
"""

import base64

from fastapi.testclient import TestClient

from api.main import app
from api.state import get_kb, get_object_store

client = TestClient(app)

# a tiny fake PNG payload (bytes need not be a real image for the store)
_IMG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n fake image bytes").decode()


def _pdf_payload():
    return {
        "kind": "pdf_batch",
        "payload": {
            "documents": [
                {
                    "doc_id": "report-q3",
                    "title": "Q3 Report",
                    "pages": [
                        {
                            "page": 12,
                            "text": "Group revenue grew in the third quarter across all regions.",
                            "tables": [{"caption": "Revenue by quarter",
                                        "rows": [["Q1", "3.1"], ["Q3", "4.2"]]}],
                            "figures": [{"caption": "Revenue trend chart",
                                         "image_b64": _IMG_B64, "bbox": "88,204,512,470"}],
                        }
                    ],
                }
            ]
        },
    }


def test_pdf_ingest_reports_stats():
    r = client.post("/ingest", json=_pdf_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert "chunks" in body["detail"] and "figures" in body["detail"]


def test_pdf_chunks_are_searchable_with_types_and_provenance():
    client.post("/ingest", json=_pdf_payload())
    r = client.post("/search", json={"query": "revenue third quarter", "top_k": 5})
    assert r.status_code == 200
    units = r.json()["units"]
    assert units
    types = {u["type"] for u in units}
    assert types & {"pdf_chunk", "table_row", "chart_caption"}
    # provenance resolves to the exact page
    assert any((u["provenance"] or {}).get("locator", "").startswith("page=12") for u in units)


def test_figure_image_stored_and_caption_linked():
    client.post("/ingest", json=_pdf_payload())
    # one image blob stored
    assert len(get_object_store()) == 1
    r = client.post("/search", json={"query": "revenue trend chart", "top_k": 5})
    caps = [u for u in r.json()["units"] if u["type"] == "chart_caption"]
    assert caps
    assert (caps[0]["provenance"] or {}).get("prov_o", {}).get("image_ref", "").startswith("obj://")


def test_generated_namespace_emitted_and_served():
    client.post("/ingest", json=_pdf_payload())
    kb = get_kb()
    assert kb.count("generated") >= 2  # doc index + at least one page summary
    # doc-level summary page is served
    r = client.get("/kb/generated/report-q3/index.md")
    assert r.status_code == 200
    page = r.json()
    assert page["namespace"] == "generated"
    assert "Q3 Report" in page["body"]
    # per-page summary references the figure and table
    r2 = client.get("/kb/generated/report-q3/page-12.md")
    assert r2.status_code == 200
    assert "Figure:" in r2.json()["body"]


def test_authored_pages_served_after_markdown_ingest(sample_kb):
    # sample_kb ingested via the fixture (index only); ingest over HTTP to populate KB.
    client.post(
        "/ingest",
        json={"kind": "markdown_tree", "namespace": "authored", "payload": {"pages": [
            {"path": "investments/isas/index.md", "frontmatter": {"title": "ISAs"},
             "body": "# ISAs\n\nAn ISA is a tax-efficient savings account."}
        ]}},
    )
    r = client.get("/kb/authored/investments/isas/index.md")
    assert r.status_code == 200
    assert r.json()["namespace"] == "authored"
    assert "ISA" in r.json()["body"]
