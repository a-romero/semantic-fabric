"""Dense-PDF ingestion (Phase 2).

Explodes each document into typed, cheap-to-retrieve artifacts and emits a
human-readable summary tree into the generated/ KB namespace:

    prose   -> pdf_chunk    (embedded + BM25)
    tables  -> table_row    (retrievable; one unit per table)
    figures -> chart_caption (VLM/-provided caption, embedded) + image in object store
    per doc -> generated/<doc_id>/index.md  and  generated/<doc_id>/page-<n>.md

Phase 2 accepts a PRE-PARSED payload so the whole downstream is testable without a
PDF library or vision model (the dependency-free path):

    {"kind": "pdf_batch", "payload": {"documents": [
        {"doc_id": "report-q3", "title": "Q3 Report", "pages": [
            {"page": 1,
             "text": "...prose...",
             "tables": [{"caption": "Revenue", "rows": [["Q1","3.1"],["Q3","4.2"]]}],
             "figures": [{"caption": "Revenue chart", "image_b64": "...",
                          "bbox": "88,204,512,470"}]}]}]}}

A real layout parser (PyMuPDF/pdfplumber) that produces this structure from raw PDF
bytes is the pluggable optional layer; it does not change anything below.
"""

from __future__ import annotations

from fabric_client.models import IngestRequest

from kb.store import KBStore
from retrieval.chunking import MAX_CHARS, Chunk, _split_by_length
from retrieval.index import RetrievalIndex

from .object_store import ObjectStore, decode_b64
from .vlm import Captioner, NullCaptioner


def _table_text(table: dict) -> str:
    caption = table.get("caption", "")
    rows = table.get("rows") or []
    body = "\n".join(" | ".join(str(c) for c in row) for row in rows)
    return f"{caption}\n{body}".strip()


def ingest_pdf_batch(
    index: RetrievalIndex,
    kb: KBStore,
    object_store: ObjectStore,
    req: IngestRequest,
    captioner: Captioner | None = None,
) -> dict:
    """Ingest a pre-parsed pdf_batch. Returns counts for the job detail."""
    captioner = captioner or NullCaptioner()
    docs = req.payload.get("documents") or []
    if not isinstance(docs, list):
        raise ValueError("payload.documents must be a list")

    n_chunks = n_figures = n_tables = n_generated = 0

    for doc in docs:
        doc_id = doc["doc_id"]
        doc_title = str(doc.get("title") or doc_id)
        doc_path = f"{doc_id}.pdf"
        chunks: list[Chunk] = []
        page_summaries: list[tuple[int, str]] = []

        for page in doc.get("pages") or []:
            n = int(page.get("page", 0))
            loc = f"page={n}"
            summary_bits: list[str] = []

            # prose -> pdf_chunk(s)
            for i, piece in enumerate(_split_by_length(page.get("text") or "", MAX_CHARS)):
                chunks.append(
                    Chunk(
                        id=f"{doc_path}#p{n}-t{i}",
                        namespace="pdf",
                        path=doc_path,
                        page_title=doc_title,
                        section_title=f"page {n}",
                        text=piece,
                        etype="pdf_chunk",
                        source_id=doc_path,
                        override_locator=loc,
                    )
                )
            if page.get("text"):
                summary_bits.append(" ".join((page["text"]).split())[:200])

            # tables -> table_row units
            for ti, table in enumerate(page.get("tables") or []):
                text = _table_text(table)
                chunks.append(
                    Chunk(
                        id=f"{doc_path}#p{n}-tab{ti}",
                        namespace="pdf",
                        path=doc_path,
                        page_title=doc_title,
                        section_title=f"page {n} table",
                        text=text,
                        etype="table_row",
                        source_id=doc_path,
                        override_locator=f"{loc};table={ti}",
                    )
                )
                n_tables += 1
                if table.get("caption"):
                    summary_bits.append(f"Table: {table['caption']}")

            # figures -> object store + chart_caption
            for fi, fig in enumerate(page.get("figures") or []):
                image = decode_b64(fig["image_b64"]) if fig.get("image_b64") else None
                ref = object_store.put(image, suffix=".png") if image else None
                caption = captioner.caption(image=image, provided=fig.get("caption"))
                bbox = fig.get("bbox")
                figloc = f"{loc};bbox={bbox}" if bbox else loc
                chunks.append(
                    Chunk(
                        id=f"{doc_path}#p{n}-fig{fi}",
                        namespace="pdf",
                        path=doc_path,
                        page_title=doc_title,
                        section_title=f"page {n} figure",
                        text=caption,
                        etype="chart_caption",
                        source_id=doc_path,
                        override_locator=figloc,
                        image_ref=ref,
                    )
                )
                n_figures += 1
                summary_bits.append(f"Figure: {caption}")

            # per-page generated summary page
            page_summary = "\n\n".join(summary_bits) or "(no extractable content)"
            page_summaries.append((n, page_summary))
            kb.put(
                "generated",
                f"{doc_id}/page-{n}.md",
                body=f"# {doc_title} — page {n}\n\n{page_summary}\n",
                frontmatter={"title": f"{doc_title} — page {n}", "source": doc_path, "page": n},
            )
            n_generated += 1

        n_chunks += index.add_chunks(chunks)

        # doc-level generated summary (index of the summary tree)
        toc = "\n".join(
            f"- [page {n}](generated/{doc_id}/page-{n}.md): "
            f"{s.splitlines()[0][:80] if s else ''}"
            for n, s in page_summaries
        )
        kb.put(
            "generated",
            f"{doc_id}/index.md",
            body=f"# {doc_title}\n\nGenerated summary of `{doc_path}`.\n\n{toc}\n",
            frontmatter={"title": doc_title, "source": doc_path, "pages": len(page_summaries)},
        )
        n_generated += 1

    return {
        "docs": len(docs),
        "chunks": n_chunks,
        "tables": n_tables,
        "figures": n_figures,
        "generated_pages": n_generated,
    }
