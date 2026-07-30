# tool-server.Dockerfile — the trusted container: owns the real
# sqlite3.Connection, runs the actual CRM SQL. Same image regardless of
# which surface (Python/JS/TS/JSON-MCP) is under test for a given episode;
# only the bind-mounted DB file differs.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn fastapi-mcp

# Preserve the src/ layout so the existing `from src.core...`/`from src.db...`
# absolute imports work unchanged.
# NOTE: src/db/scenarios/crm_scenario/tasks/ (the task generator + 90 frozen
# JSON files) is copied along with the rest of src/db/ but is never touched
# at runtime here — tasks are selected/seeded on the host, not inside this
# container. Left as one COPY for now since I can't verify a narrower COPY
# against a real `docker build` without the daemon running; safe to trim
# once that's available.
COPY src/core/ src/core/
COPY src/db/ src/db/
COPY src/tool_server/ src/tool_server/
# config.py lives at the repo root and is imported as a top-level module
# (crm_db.py does `from config import SIM_TODAY`), so it has to land next to
# src/ inside /app or the server won't import at all.
COPY config.py .

EXPOSE 8000

ENTRYPOINT ["python", "-m", "src.tool_server.server"]
CMD ["--db-path", "/data/world.sqlite", "--port", "8000"]
