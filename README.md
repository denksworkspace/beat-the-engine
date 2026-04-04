# AI-Assisted Chess Reflection Training App (MVP)

Specification sources:
- `chess_app_spec_filled.xlsx`
- `Test Strategy Template - Chess App Filled.docx`

## Architecture
- `apps/api`: FastAPI backend (API -> Service -> Repository -> Model)
- `workers/engine`: chess analysis worker
- `workers/reflection`: reflection generation worker
- `apps/web`: MVP React client
- `infra/docker-compose.yml`: local stack (postgres, redis, workers, api)

## Core Flows Implemented
- Session create/resume (`FR-1`, `FR-2`, `NFR-3`)
- Candidate workspace autosave (`FR-4`, `FR-5`)
- Commit + engine analysis + reflection (`FR-6`, `FR-7`, `FR-8`)
- Challenge mode reasoning gate (`FR-9`, `FR-10`, `NFR-8`, `NFR-9`)
- History replay + metrics (`FR-11`, `FR-12`, `NFR-10`)

## Run Locally (Docker)
```bash
cd infra
docker compose up --build
```

API health:
```bash
curl http://localhost:8000/health
```

## Run API tests
```bash
cd apps/api
python3 -m pip install -r requirements.txt
pytest -q
```

## API Endpoints
- `POST /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `PUT /v1/sessions/{session_id}/turns/{turn_id}/candidates`
- `POST /v1/sessions/{session_id}/turns/{turn_id}/commit`
- `GET /v1/sessions/{session_id}/history`
- `GET /v1/metrics/users/{user_id}`

All authenticated endpoints require header: `X-User-Id`.

## Traceability
- Requirement mapping and status: `docs/traceability_matrix.csv` (included in project folder)

