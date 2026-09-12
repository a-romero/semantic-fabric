.PHONY: install dev run mcp test lint contracts

install:
	pip install -e ./client && pip install -e ".[dev]"

run:
	uvicorn api.main:app --reload --port 8080

mcp:
	python -m api.mcp_server

test:
	pytest -q

lint:
	ruff check .

# Regenerate the committed EvidenceUnit JSON-Schema snapshot from the pydantic model.
contracts:
	python -c "import json; from fabric_client.models import EvidenceUnit; print(json.dumps(EvidenceUnit.model_json_schema(), indent=2))" > contracts/evidence_unit.schema.json
