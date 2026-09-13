"""Raw-PDF -> structured layout parsing (the front end to the dense-PDF pipeline).

``ingest_pdf_batch`` consumes a *pre-parsed* document structure::

    {"doc_id", "title", "pages": [{"page", "text", "tables": [...], "figures": [...]}]}

A ``PdfParser`` turns raw PDF *bytes* into exactly that structure, so a caller can POST
a PDF (``documents[].pdf_b64``) instead of pre-exploding it. Two backends behind one
protocol (same pattern as embedder / captioner / extractor):

- ``NullPdfParser`` — dependency-free default: it cannot parse bytes (no PDF library),
  so it raises a clear, actionable error. The pre-parsed ``pages`` path is unaffected,
  which is what CI exercises.
- ``PyMuPDFParser`` — optional (``.[pdf]`` extra): real layout extraction with PyMuPDF
  (``fitz``) — per-page text, tables (``page.find_tables``) and embedded figures
  (rendered to PNG, with bounding boxes). Needs the native lib, so it stays optional
  and is validated on-env, not in CI.

Selected by ``PDF_PARSER`` (``none`` default, ``pymupdf`` in deployment).
"""

from __future__ import annotations

import base64
from typing import Protocol


class PdfParserUnavailable(ValueError):
    """Raised when a raw PDF is submitted but no layout parser is installed.

    Subclasses ValueError so the /ingest handler reports it as a failed job rather
    than a 500.
    """


class PdfParser(Protocol):
    name: str

    def parse(self, data: bytes, *, doc_id: str, title: str | None = None) -> dict:
        """Return {"doc_id", "title", "pages": [...]} from raw PDF bytes."""
        ...


class NullPdfParser:
    name = "null"

    def parse(self, data: bytes, *, doc_id: str, title: str | None = None) -> dict:
        raise PdfParserUnavailable(
            "No PDF layout parser installed. Either POST a pre-parsed pdf_batch "
            "(documents[].pages), or install the .[pdf] extra and set PDF_PARSER=pymupdf."
        )


class PyMuPDFParser:
    """Layout parser backed by PyMuPDF (``fitz``)."""

    name = "pymupdf"

    def __init__(self, *, render_figures: bool = True) -> None:
        import fitz  # type: ignore  # PyMuPDF

        self._fitz = fitz
        self._render_figures = render_figures

    def parse(self, data: bytes, *, doc_id: str, title: str | None = None) -> dict:
        doc = self._fitz.open(stream=data, filetype="pdf")
        try:
            meta_title = (doc.metadata or {}).get("title")
            pages = [
                {
                    "page": i,
                    "text": page.get_text("text") or "",
                    "tables": self._tables(page),
                    "figures": self._figures(page) if self._render_figures else [],
                }
                for i, page in enumerate(doc, start=1)
            ]
        finally:
            doc.close()
        return {"doc_id": doc_id, "title": str(title or meta_title or doc_id), "pages": pages}

    @staticmethod
    def _bbox(rect) -> str:
        try:
            return f"{rect.x0:.0f},{rect.y0:.0f},{rect.x1:.0f},{rect.y1:.0f}"
        except Exception:
            return ""

    def _tables(self, page) -> list[dict]:
        out: list[dict] = []
        try:
            found = page.find_tables()
        except Exception:
            return out
        for t in getattr(found, "tables", []) or []:
            try:
                raw = t.extract()
            except Exception:
                continue
            rows = [["" if c is None else str(c) for c in row] for row in (raw or [])]
            rows = [r for r in rows if any(c.strip() for c in r)]
            if not rows:
                continue
            out.append({"caption": "", "rows": rows, "bbox": self._bbox(getattr(t, "bbox", None))})
        return out

    def _figures(self, page) -> list[dict]:
        out: list[dict] = []
        try:
            images = page.get_images(full=True)
        except Exception:
            return out
        for img in images:
            xref = img[0]
            try:
                pix = self._fitz.Pixmap(page.parent, xref)
                if pix.n - pix.alpha >= 4:  # CMYK / other -> RGB for PNG encoding
                    pix = self._fitz.Pixmap(self._fitz.csRGB, pix)
                png = pix.tobytes("png")
            except Exception:
                continue
            bbox = ""
            try:
                rects = page.get_image_rects(xref)
                if rects:
                    bbox = self._bbox(rects[0])
            except Exception:
                pass
            out.append({
                "caption": "",
                "image_b64": base64.b64encode(png).decode(),
                "bbox": bbox,
            })
        return out


def build_pdf_parser(kind: str | None) -> PdfParser:
    """Factory from PDF_PARSER. Falls back to the null parser if PyMuPDF is absent."""
    choice = (kind or "none").strip().lower()
    if choice in {"pymupdf", "fitz", "mupdf"}:
        try:
            return PyMuPDFParser()
        except Exception:
            return NullPdfParser()
    return NullPdfParser()
