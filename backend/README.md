# ReelMind Backend

FastAPI + Celery + Redis backend for the ReelMind iOS app.

## Folder Structure

```
backend/
├── main.py                   ← FastAPI app entry point
├── config.py                 ← Loads env vars from .env
├── supabase_client.py        ← Supabase client (service role key)
├── requirements.txt          ← Python dependencies
├── docker-compose.yml        ← Local Redis container
├── api/
│   └── v1/
│       ├── __init__.py       ← Router aggregator
│       ├── health.py         ← GET /api/v1/health
│       └── reels.py          ← POST /api/v1/reels
├── workers/
│   ├── celery_app.py         ← Celery configuration
│   └── tasks.py              ← Background task definitions
├── schemas/
│   └── reel.py               ← Pydantic models
└── services/                 ← Business logic (Phase 2+)
```

## Local Development Setup

### 1. Create Python virtual environment

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in real credentials
```

### 3. Start Redis (Docker)

```bash
docker compose up -d
```

Verify Redis is running:
```bash
docker compose ps
# Should show reelmind-redis as "healthy"
```

### 4. Start the FastAPI server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit:
- http://localhost:8000 — Service info
- http://localhost:8000/docs — Interactive API docs (Swagger UI)
- http://localhost:8000/api/v1/health — Health check

### 5. Start Celery worker (separate terminal)

```bash
source venv/bin/activate
celery -A workers.celery_app worker --loglevel=info
```

You should see output like:
```
[tasks]
  . workers.tasks.ping
  . workers.tasks.process_reel
celery@hostname ready.
```

### 6. Smoke test the worker

In a Python REPL:
```python
from workers.tasks import ping
result = ping.delay()
print(result.get(timeout=5))  # Should print: pong
```

## Stopping Services

```bash
# Stop FastAPI: Ctrl+C in its terminal
# Stop Celery: Ctrl+C in its terminal
# Stop Redis:
docker compose down
```

## Production Notes

- **Cloud Redis**: Before deployment, switch `REDIS_URL` to a managed cloud Redis (Upstash, Redis Cloud, etc.). See `backlog.md`.
- **Process Manager**: Use a process manager (systemd, supervisord, Railway/Render's built-in) to run `uvicorn` and `celery worker` as separate services.
- **Environment**: Set `ENVIRONMENT=production` to disable debug mode and lock down CORS.

## Troubleshooting

**`ImportError: No module named 'X'`**
→ Virtual env isn't active or deps not installed. Run `source venv/bin/activate && pip install -r requirements.txt`.

**Celery worker can't connect to Redis**
→ Verify Redis is running: `docker compose ps`. Check `REDIS_URL` in `.env` matches `redis://localhost:6379`.

**`EnvironmentError: Missing required environment variables`**
→ `.env` file isn't filled in. Check `.env.example` for the full list.
