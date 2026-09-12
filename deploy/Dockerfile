FROM python:3.11-slim

WORKDIR /app
COPY client/ ./client/
COPY pyproject.toml ./
COPY api/ ./api/
COPY ingest/ ./ingest/
COPY retrieval/ ./retrieval/
COPY graph/ ./graph/
COPY reasoning/ ./reasoning/
COPY provenance/ ./provenance/

RUN pip install --no-cache-dir ./client && pip install --no-cache-dir fastapi "uvicorn[standard]"

EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
