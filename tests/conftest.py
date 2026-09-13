"""Shared test fixtures.

Each test gets a fresh in-memory RetrievalIndex so state never leaks between tests,
and a small authored KB it can ingest.
"""

import pytest

from api import state
from retrieval.embedder import HashingEmbedder
from retrieval.index import RetrievalIndex
from retrieval.vector_store import InMemoryVectorStore

SAMPLE_PAGES = [
    {
        "path": "investments/isas/index.md",
        "frontmatter": {"title": "ISAs", "summary": "Individual Savings Accounts explained."},
        "body": (
            "# ISAs\n\n"
            "An ISA is a tax-efficient individual savings account for UK savers.\n\n"
            "## Types\n\n"
            "Cash ISA and stocks and shares ISA are the main types. A stocks and "
            "shares ISA invests in funds and equities.\n"
        ),
    },
    {
        "path": "insurance/home/index.md",
        "frontmatter": {"title": "Home Insurance"},
        "body": (
            "# Home Insurance\n\n"
            "Home insurance covers your home and contents against damage and theft.\n"
        ),
    },
]


@pytest.fixture(autouse=True)
def fresh_index():
    """Reset the API's shared stores to clean in-memory instances per test."""
    from extraction.extractor import NullExtractor
    from ingest.object_store import InMemoryObjectStore
    from ingest.pdf_parser import NullPdfParser
    from ingest.vlm import NullCaptioner
    from kb.store import KBStore
    from ontology.validator import SimpleConstraintValidator
    from provenance.store import InMemoryProvenanceStore
    from reasoning.engine import SimpleForwardChainer

    state.set_index(RetrievalIndex(HashingEmbedder(), InMemoryVectorStore()))
    state.set_kb(KBStore())
    state.set_object_store(InMemoryObjectStore())
    state.set_provenance(InMemoryProvenanceStore())
    state.set_reasoning(SimpleForwardChainer())
    state.set_validator(SimpleConstraintValidator())
    state.set_extractor(NullExtractor())
    state.set_captioner(NullCaptioner())
    state.set_pdf_parser(NullPdfParser())
    yield


@pytest.fixture
def sample_kb(fresh_index):
    """Ingest the sample authored KB into the current index."""
    state.get_index().add_pages(SAMPLE_PAGES, namespace="authored")
