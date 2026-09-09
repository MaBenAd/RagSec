> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Infrastructure & Deployment

## Services Overview

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `backend` | Custom (FastAPI) | `8000` | REST API |
| `frontend` | Custom (Next.js) | `3000` | Web UI |
| `postgres` | `postgres:15-alpine` | `5432` | Primary database |
| `redis` | `redis:7-alpine` | `6379` | Cache layer |
| `qdrant` | `qdrant/qdrant:latest` | `6333` | Vector store |

---

## Docker Compose

**File:** `docker-compose.yml`

### Backend Service
```yaml
backend:
  build:
    context: .
    dockerfile: backend/Dockerfile
  env_file: .env
  environment:
    - QDRANT_URL=http://qdrant:6333
    - DATABASE_URL=${DOCKER_DATABASE_URL:-postgresql://ensa_user:ensa_pass@postgres:5432/ensa_db}
  ports: ["8000:8000"]
  depends_on: [qdrant, postgres]
  volumes: [./backend:/app/backend]
  restart: unless-stopped
```

### Frontend Service
```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
  environment:
    - NEXT_PUBLIC_API_URL=http://backend:8000
  ports: ["3000:3000"]
  depends_on: [backend]
  restart: unless-stopped
```

### PostgreSQL Service
```yaml
postgres:
  image: postgres:15-alpine
  environment:
    - POSTGRES_USER=${POSTGRES_USER:-ensa_user}
    - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-ensa_pass}
    - POSTGRES_DB=${POSTGRES_DB:-ensa_db}
  ports: ["5432:5432"]
  volumes: [postgres_data:/var/lib/postgresql/data]
  restart: unless-stopped
```

### Redis Service
```yaml
redis:
  image: redis:7-alpine
  ports: ["6379:6379"]
  restart: unless-stopped
```

### Qdrant Service
```yaml
qdrant:
  image: qdrant/qdrant:latest
  ports: ["6333:6333"]
  volumes: [qdrant_data:/qdrant/storage]
  restart: unless-stopped
```

### Named Volumes
- `postgres_data` — PostgreSQL data directory
- `qdrant_data` — Qdrant vector storage

---

## Dockerfiles

### Backend Dockerfile (`backend/Dockerfile`)
- Base: `python:3.10-slim` (or similar)
- Copies `backend/` directory
- Installs from `requirements.docker.txt`
- CMD: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`

### Frontend Dockerfile (`frontend/Dockerfile`)
Multi-stage build:
1. **deps stage:** `node:18-alpine` — install npm deps
2. **builder stage:** `next build` with `output: "standalone"`
3. **runner stage:** minimal image serving `.next/standalone`

---

## Development Setup

### Linux / macOS — `dev.sh`

The `dev.sh` script automates the local development environment:

1. Creates `.env` from `.env.example` if missing
2. Creates Python virtual environment (`venv`) if missing
3. Installs missing Python dependencies
4. Starts Docker services: `postgres`, `redis`, `qdrant`
5. Runs DB bootstrap: `python backend/scripts/bootstrap_dev_content.py`
6. Starts backend: `uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
7. Starts frontend: `cd frontend && npm install && npm run dev`

```bash
bash ./dev.sh
```

### Windows — `dev.ps1`

PowerShell equivalent of `dev.sh`:
- Same steps adapted for Windows paths and commands
- Uses `python` instead of `python3`

```powershell
.\dev.ps1
```

### Manual Setup

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with real values

# 2. Python virtualenv
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start infrastructure services
docker compose up -d postgres redis qdrant

# 5. Initialize database and seed data
PYTHONPATH=. python backend/scripts/bootstrap_dev_content.py

# 6. Start backend (terminal 1)
PYTHONPATH=. uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# 7. Start frontend (terminal 2)
cd frontend && npm install && npm run dev
```

---

## Production Deployment

### Full Docker Stack

```bash
# Build and start all services
docker compose up -d --build

# Initialize database
docker compose exec backend python backend/scripts/bootstrap_dev_content.py

# Import timetable seeds
docker compose exec backend python backend/scripts/seed_timetables.py --replace

# Build FAQ vector index
docker compose exec backend python backend/scripts/rebuild_faq_index.py
```

### Service URLs

| Service | URL |
|---------|-----|
| Frontend | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| Swagger Docs | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Qdrant | `http://localhost:6333` |

---

## CI/CD — GitHub Actions

**File:** `.github/workflows/main.yml`

### Triggers
- Push to `main` branch
- Pull requests to `main`

### Jobs

#### 1. Backend Tests
```yaml
- uses: actions/setup-python@v4
  with: {python-version: "3.10"}
- run: pip install -r requirements.txt
- run: PYTHONPATH=. pytest backend/tests/ -v
```

#### 2. Frontend Build
```yaml
- uses: actions/setup-node@v3
  with: {node-version: "18"}
- run: cd frontend && npm install && npm run build
```

#### 3. Docker Image Build
- Builds `backend/Dockerfile` and `frontend/Dockerfile`
- Validates that images build successfully
- (Optional: push to container registry if configured)

---

## Environment Variable Reference

### Required Variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | GroqCloud API key for LLM access |
| `JWT_SECRET_KEY` | JWT signing secret (≥32 random characters) |
| `DATABASE_URL` | PostgreSQL connection string (local dev) |
| `DOCKER_DATABASE_URL` | PostgreSQL URL for Docker (uses `postgres` hostname) |
| `ADMIN_PASSWORD` | Initial admin account password |
| `POSTGRES_USER` | PostgreSQL username |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_DB` | PostgreSQL database name |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | GroqCloud model name |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token lifetime |
| `REDIS_HOST` | `127.0.0.1` (local) / `redis` (Docker) | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `ENABLE_CACHE` | `true` | Enable/disable Redis caching |
| `CACHE_TTL` | `3600` | Cache time-to-live (seconds) |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins (comma-separated) |
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant server URL |
| `VECTORSTORE_PATH` | `backend/data/vectorstore_qdrant` | Local Qdrant storage path |
| `CHAT_TIMEOUT_SECONDS` | `90` | LLM call timeout |
| `ENABLE_RAG_FALLBACK` | `false` | Lexical search fallback if Qdrant fails |
| `APP_TIMEZONE` | `Africa/Casablanca` | Timezone for date parsing |
| `ENV` | `dev` | Set to `production` to enable secure cookies |

---

## Data Persistence & Shared Sources of Truth

| Data | Storage | Git-Versioned |
|------|---------|---------------|
| User accounts, conversations, messages | PostgreSQL (Docker volume) | No |
| FAQ documents | `backend/data/faq/` | Yes (PDFs, JSON) |
| Timetable seeds | `backend/data/seeds/timetables.json` | Yes |
| Vector index | `backend/data/vectorstore_qdrant/` | No (rebuilt) |
| Application logs | `backend/data/logs/app.log` | No |
| Redis cache | In-memory (no persistence configured) | No |

---

## Utility Scripts

| Script | Command | Purpose |
|--------|---------|---------|
| `bootstrap_dev_content.py` | `python backend/scripts/bootstrap_dev_content.py` | Full init: DB + admin seed + timetables + FAQ index |
| `seed_timetables.py` | `python backend/scripts/seed_timetables.py [--replace]` | Import timetables from JSON seed to DB |
| `export_timetables_seed.py` | `python backend/scripts/export_timetables_seed.py` | Export timetables from DB to JSON seed |
| `rebuild_faq_index.py` | `python backend/scripts/rebuild_faq_index.py` | Rebuild Qdrant vector index from FAQ files |
| `rag_pdf_benchmark.py` | `python backend/scripts/rag_pdf_benchmark.py` | Benchmark RAG quality on PDF sources |

**Note:** All scripts must be run with `PYTHONPATH=.` from the project root.

---

## Network Architecture (Docker)

```
[Browser]
    │
    │ HTTP :3000
    ▼
[frontend container]
    │
    │ HTTP :8000 (internal Docker network: backend:8000)
    ▼
[backend container]
    ├── postgres:5432 (internal)
    ├── redis:6379 (internal)
    └── qdrant:6333 (internal)
```

The frontend receives `NEXT_PUBLIC_API_URL=http://backend:8000` at build time, which routes all API calls to the backend container over the internal Docker network.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'backend'` | Set `PYTHONPATH=.` before running |
| Qdrant connection failed | Check `QDRANT_URL` env var, ensure `qdrant` Docker container is running |
| Redis connection failed | Check `REDIS_HOST`/`REDIS_PORT`, ensure `redis` Docker container is running |
| JWT token expired immediately | Verify `ACCESS_TOKEN_EXPIRE_MINUTES` and server clock sync |
| Frontend can't reach backend | Verify `NEXT_PUBLIC_API_URL` and `CORS_ORIGINS` settings |
| Database locked (SQLite only) | Stop all instances, delete `.db-journal` files |
| FAQ not found in vector DB | Run `backend/scripts/rebuild_faq_index.py` |
| Admin login fails | Check `ADMIN_PASSWORD` in `.env`, run `bootstrap_dev_content.py` |
| PostgreSQL migration error | Check Alembic head: `cd backend && alembic current` |
