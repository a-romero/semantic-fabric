"""Figure/chart captioner behind one protocol.

- ``NullCaptioner`` — dependency-free default: uses a caption supplied with the figure
  (as in a pre-parsed pdf_batch payload) or a placeholder. Lets the whole figure
  branch run and be tested without a vision model.
- A real VLM captioner (generating a caption from image bytes) is added with the
  deployment; like BGE-M3 it needs model access, so it stays optional and pluggable.
"""

from __future__ import annotations

from typing import Protocol


class Captioner(Protocol):
    def caption(self, *, image: bytes | None, provided: str | None) -> str: ...


class NullCaptioner:
    def caption(self, *, image: bytes | None, provided: str | None) -> str:
        return (provided or "").strip() or "[figure: no caption available]"
