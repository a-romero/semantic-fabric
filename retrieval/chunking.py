"""Split authored Markdown pages into retrievable chunks with provenance.

Phase 1 keeps this deliberately simple: split on Markdown headings, then bound each
section by character length. Entity-/ontology-aware splitting (semantica.split) comes
with Phase 2's dense-source pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
MAX_CHARS = 1200


@dataclass
class Chunk:
    id: str
    namespace: str
    path: str
    page_title: str
    section_title: str
    text: str
    frontmatter: dict[str, Any] = field(default_factory=dict)

    @property
    def locator(self) -> str:
        anchor = self.section_title.strip().lower().replace(" ", "-")
        return f"{self.path}#{anchor}" if anchor else self.path


def _split_by_length(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    # split on blank lines, packing paragraphs up to max_chars
    parts, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        if not para.strip():
            continue
        if len(buf) + len(para) + 2 > max_chars and buf:
            parts.append(buf.strip())
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf.strip():
        parts.append(buf.strip())
    return parts


def chunk_page(namespace: str, path: str, frontmatter: dict, body: str) -> list[Chunk]:
    """Chunk a single Markdown page into a list of Chunk records."""
    page_title = str(frontmatter.get("title") or path)
    chunks: list[Chunk] = []

    # Find heading spans; text before the first heading is the intro section.
    matches = list(_HEADING.finditer(body))
    spans: list[tuple[str, str]] = []
    if not matches:
        spans.append((page_title, body))
    else:
        if matches[0].start() > 0:
            spans.append((page_title, body[: matches[0].start()]))
        for i, m in enumerate(matches):
            section_title = m.group(2).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            spans.append((section_title, body[start:end]))

    n = 0
    for section_title, section_text in spans:
        for piece in _split_by_length(section_text):
            chunks.append(
                Chunk(
                    id=f"{namespace}:{path}#{n}",
                    namespace=namespace,
                    path=path,
                    page_title=page_title,
                    section_title=section_title,
                    text=piece,
                    frontmatter=frontmatter,
                )
            )
            n += 1
    return chunks
