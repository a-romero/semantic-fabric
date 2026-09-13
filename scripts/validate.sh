#!/usr/bin/env bash
# On-env validation for semantic-fabric's real backends.
#
# CI runs the pure-Python defaults only. This script installs the optional extras and
# runs the opt-in test suites that exercise the REAL backends — Qdrant, BGE-M3, the
# semantica layers (PROV-O provenance, Datalog reasoning, SHACL), and LiteLLM
# extraction — which need models/services/credentials CI does not have.
#
# Usage:
#   scripts/validate.sh                # runs whatever your env supports (others skip)
#   EXTRACTION_MODEL=openai/gpt-4o-mini scripts/validate.sh
#
# Each layer runs only if its dependency + credential are present; anything missing
# SKIPS with a reason rather than failing. A failure means a real backend is broken.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/3 install (client + dev + prod + semantica + llm) =="
pip install -q -e ./client
pip install -q -e ".[dev,prod,semantica,llm]" || {
  echo "!! full extras install failed; install what your env supports and re-run"; }

# Backend selectors so the opt-in tests light up.
export VECTOR_STORE="${VECTOR_STORE:-qdrant}"          # QdrantVectorStore uses :memory: in tests
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-BAAI/bge-m3}"
export PROVENANCE_BACKEND="${PROVENANCE_BACKEND:-semantica}"
export REASONING_BACKEND="${REASONING_BACKEND:-semantica}"
export ONTOLOGY_VALIDATOR="${ONTOLOGY_VALIDATOR:-shacl}"
export EXTRACTION_BACKEND="${EXTRACTION_BACKEND:-llm}"
export EXTRACTION_MODEL="${EXTRACTION_MODEL:-anthropic/claude-opus-5}"

# Enable the live LLM extraction test only if a credential is visible.
if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ] || [ -n "${LLM_API_BASE:-}" ]; then
  export EXTRACTION_LIVE=1
  echo "-- live LLM extraction: ENABLED (EXTRACTION_MODEL=$EXTRACTION_MODEL)"
else
  echo "-- live LLM extraction: skipped (set ANTHROPIC_API_KEY / OPENAI_API_KEY / LLM_API_BASE)"
fi

echo "== 2/3 full test suite incl. opt-in backend tests =="
PYTHONPATH=client:. pytest -q -rs \
  tests/test_qdrant.py \
  tests/test_bge_m3.py \
  tests/test_semantica_backends.py \
  tests/test_extraction.py \
  tests/     # the rest (defaults) too, for a clean full run

echo
echo "== 3/3 optional: live end-to-end smoke =="
echo "Start the service with the real backends, then exercise it, e.g.:"
cat <<'EOF'
  uvicorn api.main:app --port 8080 &   # inherits the env above
  # ingest with graph enrichment on:
  EXTRACTION_ON_INGEST=true curl -s -XPOST localhost:8080/ingest -H 'content-type: application/json' \
    -d '{"kind":"markdown_tree","namespace":"authored","payload":{"pages":[
         {"path":"investments/isas/index.md","frontmatter":{"title":"ISAs"},
          "body":"An ISA is a tax-efficient savings account offered by Aviva."}]}}'
  curl -s -XPOST localhost:8080/search  -d '{"query":"tax efficient savings","top_k":3}' -H 'content-type: application/json'
  curl -s -XPOST localhost:8080/extract -d '{"text":"Aviva offers the Enhanced Pension Annuity."}' -H 'content-type: application/json'
  curl -s -XPOST localhost:8080/reason  -d '{"query":"Insurable(p)","facts":["Policy(p)"],"rules":[{"name":"r","body":["Policy(p)"],"head":"Insurable(p)"}]}' -H 'content-type: application/json'
  DEC=$(curl -s -XPOST localhost:8080/decisions -d '{"scenario":"q","outcome":"a","evidence":["investments/isas/index.md"]}' -H 'content-type: application/json' | python -c 'import sys,json;print(json.load(sys.stdin)["decision_id"])')
  curl -s localhost:8080/decisions/$DEC/chain
EOF
echo
echo "For the skilled-agent round-trip, see VALIDATION.md."
