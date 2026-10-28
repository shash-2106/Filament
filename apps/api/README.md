# apps/api — Filament Backend Service

FastAPI backend foundation for Filament, a provenance-aware memory governance system for AI agents.

---

## Current Status

* **Status:** Backend Foundation Scaffolding Complete.
* **Interpreter:** Python 3.12 (`Python 3.12.13` verified in `.venv`).
* **Framework:** FastAPI with Pydantic Settings (`pydantic-settings`), SQLAlchemy 2.x, asyncpg, Alembic, and pytest.

---

## Directory Layout

```text
apps/api/
├── pyproject.toml              # Package definition, dependencies, and pytest configuration
├── alembic.ini                 # Database migration configuration
├── alembic/                    # Alembic migration environment and script templates
│   ├── env.py
│   └── script.py.mako
├── src/
│   └── filament_api/
│       ├── __init__.py
│       ├── main.py             # FastAPI entrypoint, lifespan manager, and CORS middleware
│       ├── config.py           # Environment-driven settings via Pydantic Settings
│       ├── api/
│       │   ├── __init__.py     # Unified API router
│       │   └── routes/
│       │       ├── __init__.py
│       │       └── health.py   # GET /api/v1/health route handler
│       ├── db/
│       │   ├── __init__.py
│       │   ├── base.py         # SQLAlchemy 2.x DeclarativeBase
│       │   └── session.py      # Async engine and session lifecycle dependencies
│       └── schemas/
│           ├── __init__.py
│           └── health.py       # Pydantic schemas for health endpoint
└── tests/
    ├── __init__.py
    ├── conftest.py             # Pytest fixtures (ASGI AsyncClient, mock settings)
    └── test_health.py          # Liveliness, OpenAPI, and configuration test suite
```

---

## Local Development

### 1. Environment Setup
The backend utilizes Python 3.12:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Running the Development Server
```bash
uvicorn filament_api.main:app --reload --host 127.0.0.1 --port 8000
```
* **Interactive Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **OpenAPI JSON:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)
* **Health Endpoint:** [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

### 3. Running Automated Tests
```bash
pytest
```
* Tests execute entirely in-process using HTTPX's `ASGITransport` without requiring a live PostgreSQL instance or network access.
