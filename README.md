# JIS ChatSQL Gateway

Safe SQL gateway for JIS-ChatSQL (Project #1 of the agent factory).

## Purpose

This service exposes a controlled HTTP API for Flowise:

- readonly SQL execution (`SELECT` only)
- row/time limits
- basic schema discovery
- JSONL audit log

This avoids direct DB access from the chat layer and removes dependency on manual SSH tunnels.

## Endpoints

- `GET /health`
- `GET /schema/tables?limit=200`
- `POST /query`

### Example `/query` payload

```json
{
  "request_id": "REQ-20260323-0001",
  "caller": "flowise",
  "sql": "SELECT NOW() AS ts, DATABASE() AS db"
}
```

## Local run

1. Create virtual env and install dependencies.
2. Copy `.env.example` to `.env` and update values.
3. Run:

```bash
uvicorn src.app:app --host 127.0.0.1 --port 8093
```

## Docker run

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

## Security guardrails

- single SQL statement only
- `SELECT` only
- blocked mutating keywords
- optional allowlist (`SQL_REQUIRE_ALLOWLIST=true`)
- `MAX_EXECUTION_TIME` per session
- max rows cap

## Notes

- Keep production credentials in environment variables/secrets manager.
- Do not commit `.env` files.
- Rotate any credential that was previously shared in chat/logs.
