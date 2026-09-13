"""Figure captioner wiring + on-env VLM captioning.

CI-safe: the null default, the build factory, and that ingestion routes uncaptioned
figures through the injected captioner. The real LiteLLM vision captioner is validated
on-env (test_llm_captioner_live), gated like the extraction live test.
"""

import base64
import os

import pytest
from fastapi.testclient import TestClient

from api import state
from api.main import app
from ingest.vlm import NullCaptioner, build_captioner

client = TestClient(app)
_IMG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n fake").decode()


_PLACEHOLDER = "[figure: no caption available]"


def _have_litellm() -> bool:
    import importlib.util

    return importlib.util.find_spec("litellm") is not None


def test_null_captioner_and_factory():
    assert build_captioner(None).caption(image=None, provided=None) == _PLACEHOLDER
    assert build_captioner(None).caption(image=None, provided="Given") == "Given"
    # build("llm") -> LLMCaptioner where litellm is installed, else null fallback.
    picked = build_captioner("llm")
    if _have_litellm():
        assert picked.__class__.__name__ == "LLMCaptioner"
    else:
        assert isinstance(picked, NullCaptioner)


def test_ingestion_captions_uncaptioned_figures_via_injected_captioner():
    class _StubCaptioner:
        name = "stub"

        def caption(self, *, image, provided):
            if provided and provided.strip():
                return provided.strip()
            return "VLM: a bar chart of revenue"

    state.set_captioner(_StubCaptioner())
    payload = {
        "kind": "pdf_batch",
        "payload": {"documents": [{
            "doc_id": "d", "title": "D", "pages": [{
                "page": 1, "text": "prose",
                "figures": [{"image_b64": _IMG_B64}],  # NO provided caption
            }],
        }]},
    }
    assert client.post("/ingest", json=payload).status_code == 200
    r = client.post("/search", json={"query": "bar chart revenue", "top_k": 5})
    caps = [u for u in r.json()["units"] if u["type"] == "chart_caption"]
    assert caps and caps[0]["content"] == "VLM: a bar chart of revenue"


@pytest.mark.skipif(
    not os.getenv("CAPTION_LIVE"),
    reason="set CAPTION_LIVE=1 (+ CAPTION_MODEL and provider creds) for the live VLM test",
)
def test_llm_captioner_live():
    pytest.importorskip("litellm")
    from ingest.vlm import LLMCaptioner

    # An 8x8 red PNG (valid image bytes) so a real vision model has something to look at.
    red = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFElEQVR4nGP8z8Dwn4EIwDiqkL4KAV"
        "6eAgVHwn9wAAAAAElFTkSuQmCC"
    )
    # Use _complete (no swallow) so a real API error surfaces in the test instead of
    # being masked as the placeholder.
    cap = LLMCaptioner()._complete(red)
    assert cap, "vision model returned empty output (raise CAPTION_MAX_TOKENS?)"
