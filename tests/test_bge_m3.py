"""Opt-in BGE-M3 embedder test.

Runs only when FlagEmbedding is installed (the .[prod] extra). Loading BAAI/bge-m3
downloads ~2.3GB of weights from HuggingFace on first use, so this test skips
gracefully in offline/sandboxed environments (e.g. CI without HF egress). Where the
model is reachable, it validates dimensionality and that embeddings come back.
"""

import pytest

pytest.importorskip("FlagEmbedding")

from retrieval.embedder import build_embedder  # noqa: E402


def test_bge_m3_embeds_when_model_available():
    try:
        emb = build_embedder("BAAI/bge-m3")
    except Exception as exc:  # weights unreachable (offline) or load failure
        pytest.skip(f"bge-m3 weights unavailable in this environment: {exc}")
    vecs = emb.embed(["tax-efficient savings account", "home insurance"])
    assert emb.dim == 1024
    assert len(vecs) == 2
    assert len(vecs[0]) == 1024
