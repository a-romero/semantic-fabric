"""Figure/chart captioner behind one protocol.

- ``NullCaptioner`` — dependency-free default: uses a caption supplied with the figure
  (as in a pre-parsed pdf_batch payload) or a placeholder. Lets the whole figure
  branch run and be tested without a vision model.
- ``LLMCaptioner`` — optional (``.[llm]`` extra): a provider-agnostic vision captioner
  via LiteLLM (Anthropic / OpenAI / Ollama-llava / proxy, chosen by ``CAPTION_MODEL``).
  It describes a figure from its image bytes when no caption was supplied. Needs a
  vision-capable model + credentials, so it stays optional and is validated on-env.

Selected by ``CAPTION_BACKEND`` (``null`` default, ``llm`` in deployment).
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)

_PLACEHOLDER = "[figure: no caption available]"

_DEFAULT_PROMPT = (
    "You are captioning a figure extracted from a document for retrieval. In one or two "
    "sentences, describe what the figure shows — its type (chart, diagram, photo, table "
    "image), the quantities or entities depicted, and any clear trend or takeaway. Reply "
    "with the caption text only."
)


class Captioner(Protocol):
    def caption(self, *, image: bytes | None, provided: str | None) -> str: ...


class NullCaptioner:
    name = "null"

    def caption(self, *, image: bytes | None, provided: str | None) -> str:
        return (provided or "").strip() or _PLACEHOLDER


class LLMCaptioner:
    """Vision captioner over LiteLLM. Prefers an author-supplied caption when present."""

    name = "llm"

    def __init__(
        self,
        model: str | None = None,
        *,
        prompt: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        import litellm  # type: ignore

        self._litellm = litellm
        self.model = model or os.getenv("CAPTION_MODEL", "openai/gpt-4o-mini")
        self._prompt = prompt or _DEFAULT_PROMPT
        self._api_base = api_base or os.getenv("LLM_API_BASE")
        self._api_key = api_key or os.getenv("LLM_API_KEY")
        # A caption is short, but reasoning models (e.g. gpt-5.x) spend the budget on
        # hidden reasoning tokens first — too small a cap yields empty output — so the
        # default is generous and overridable.
        self._max_tokens = max_tokens or int(os.getenv("CAPTION_MAX_TOKENS", "1024"))

    def _complete(self, image: bytes) -> str:
        """Call the vision model and return its text. Raises on API error (no swallow)."""
        b64 = base64.b64encode(image).decode()
        kwargs: dict = {"model": self.model, "max_tokens": self._max_tokens,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": self._prompt},
                                {"type": "image_url",
                                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
                            ],
                        }]}
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key
        resp = self._litellm.completion(**kwargs)
        return (resp.choices[0].message.content or "").strip()

    def caption(self, *, image: bytes | None, provided: str | None) -> str:
        # An author/layout-supplied caption is cheaper and exact — prefer it.
        if provided and provided.strip():
            return provided.strip()
        if not image:
            return _PLACEHOLDER
        try:
            text = self._complete(image)
        except Exception as exc:
            # Ingestion must not crash on a caption failure — fall back, but say why.
            logger.warning("VLM caption call failed (%s); using placeholder.", exc)
            return _PLACEHOLDER
        if not text:
            logger.warning("VLM caption returned empty content (raise CAPTION_MAX_TOKENS "
                           "for reasoning models); using placeholder.")
        return text or _PLACEHOLDER


def build_captioner(kind: str | None) -> Captioner:
    """Factory from CAPTION_BACKEND. Falls back to the null captioner if litellm absent."""
    choice = (kind or "null").strip().lower()
    if choice in {"llm", "vlm", "litellm"}:
        try:
            return LLMCaptioner()
        except Exception:
            return NullCaptioner()
    return NullCaptioner()
