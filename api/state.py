"""Process-shared stores for the API.

Phase 1 kept a single RetrievalIndex; Phase 2 adds the KB store (authored/ +
generated/ namespaces served over /kb) and an object store (figure images). All are
built lazily and reset by tests for isolation. Persistence across restarts comes with
the Qdrant / object-store backends; these singletons are thin fronts over them.
"""

from __future__ import annotations

import os

from extraction.extractor import Extractor, build_extractor
from ingest.object_store import InMemoryObjectStore, ObjectStore
from ingest.pdf_parser import PdfParser, build_pdf_parser
from ingest.vlm import Captioner, build_captioner
from kb.store import KBStore
from ontology.validator import OntologyValidator, build_ontology_validator
from provenance.store import ProvenanceStore, build_provenance_store
from reasoning.engine import ReasoningEngine, build_reasoning_engine
from retrieval.index import RetrievalIndex, build_index_from_env

_index: RetrievalIndex | None = None
_kb: KBStore | None = None
_object_store: ObjectStore | None = None
_provenance: ProvenanceStore | None = None
_reasoning: ReasoningEngine | None = None
_validator: OntologyValidator | None = None
_extractor: Extractor | None = None
_captioner: Captioner | None = None
_pdf_parser: PdfParser | None = None


def get_index() -> RetrievalIndex:
    global _index
    if _index is None:
        _index = build_index_from_env()
    return _index


def set_index(index: RetrievalIndex) -> None:
    global _index
    _index = index


def get_kb() -> KBStore:
    global _kb
    if _kb is None:
        db = os.getenv("FABRIC_DB")
        if db:
            from retrieval.persistence import get_store
            _kb = KBStore(persist=get_store(db))
            _kb.load_persisted()
        else:
            _kb = KBStore()
    return _kb


def set_kb(kb: KBStore) -> None:
    global _kb
    _kb = kb


def get_object_store() -> ObjectStore:
    global _object_store
    if _object_store is None:
        _object_store = InMemoryObjectStore()
    return _object_store


def set_object_store(store: ObjectStore) -> None:
    global _object_store
    _object_store = store


def get_provenance() -> ProvenanceStore:
    global _provenance
    if _provenance is None:
        _provenance = build_provenance_store(os.getenv("PROVENANCE_BACKEND"))
    return _provenance


def set_provenance(store: ProvenanceStore) -> None:
    global _provenance
    _provenance = store


def get_reasoning() -> ReasoningEngine:
    global _reasoning
    if _reasoning is None:
        _reasoning = build_reasoning_engine(os.getenv("REASONING_BACKEND"))
    return _reasoning


def set_reasoning(engine: ReasoningEngine) -> None:
    global _reasoning
    _reasoning = engine


def get_validator() -> OntologyValidator:
    global _validator
    if _validator is None:
        _validator = build_ontology_validator(os.getenv("ONTOLOGY_VALIDATOR"))
    return _validator


def set_validator(validator: OntologyValidator) -> None:
    global _validator
    _validator = validator


def get_extractor() -> Extractor:
    global _extractor
    if _extractor is None:
        _extractor = build_extractor(os.getenv("EXTRACTION_BACKEND"))
    return _extractor


def set_extractor(extractor: Extractor) -> None:
    global _extractor
    _extractor = extractor


def get_captioner() -> Captioner:
    global _captioner
    if _captioner is None:
        _captioner = build_captioner(os.getenv("CAPTION_BACKEND"))
    return _captioner


def set_captioner(captioner: Captioner) -> None:
    global _captioner
    _captioner = captioner


def get_pdf_parser() -> PdfParser:
    global _pdf_parser
    if _pdf_parser is None:
        _pdf_parser = build_pdf_parser(os.getenv("PDF_PARSER"))
    return _pdf_parser


def set_pdf_parser(parser: PdfParser) -> None:
    global _pdf_parser
    _pdf_parser = parser
