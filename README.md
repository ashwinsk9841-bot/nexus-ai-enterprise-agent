# NEXUS

**AI-Powered Enterprise Intelligence & Operations Platform**

NEXUS is an enterprise command center that analyzes business data, monitors
systems, detects anomalies, investigates security events, and summarizes
findings through a fleet of specialized AI agents — backed by a RAG knowledge
base and protected by human approvals and full audit logging.

---

## ONE COMMAND. ONE SERVER. ONE URL.

```bash
python app.py
```

That's it. From the project root, a single command:

1. Sets up a local SQLite demo database automatically (no Postgres needed)
2. Builds the frontend production bundle on first run (npm, one-time)
3. Starts the FastAPI backend **and** serves the built frontend from the **same process**
4. Opens **http://localhost:8000** in your browser automatically
5. Logs you in with the one-click **"Use Demo Account"** button

**No second terminal. No `uvicorn`. No `npm run dev`.**

```
Browser
   ↓
FastAPI  ← serves BOTH the frontend (dist build) and the /api endpoints
   ↓
NEXUS Backend APIs
   ↓
Services / AI Agents / Database
```

The frontend calls relative `/api/...` URLs on the same origin — same-server,
same-port, so there are no CORS issues in normal local usage.

---

## Quick Start

### Requirements

- **Python 3.11+**
- **Node.js 18+** (only needed for the *one-time* frontend build)

### 1. Install Python dependencies

```bash
python -m venv backend\.venv          # Windows
# source backend/.venv/bin/activate  # Linux/macOS
backend\.venv\Scripts\activate        # Windows
pip install -r backend\requirements.txt
```

### 2. Configure .env (optional)

```bash
copy backend\.env.example backend\.env   # Windows
# cp backend/.env.example backend/.env   # Linux/macOS
```

You can leave everything as-is. NEXUS runs out-of-the-box in **demo mode**
with a local SQLite database (`backend/nexus.db`). Set `DATABASE_URL` to
PostgreSQL when you want the production database.

### 3. Run

```bash
python app.py
```

The browser opens NEXUS automatically at **http://localhost:8000**.
Click **"Use Demo Account"** — or use one of these:

| Role    | Email            | Password    |
| ------- | ---------------- | ----------- |
| ADMIN   | demo@nexus.io    | demo1234    |
| MANAGER | manager@nexus.io | manager123  |
| ANALYST | analyst@nexus.io | analyst123  |
| VIEWER  | viewer@nexus.io  | viewer123   |

Useful URLs:

- App: http://localhost:8000
- OpenAPI/Swagger docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

### When does it rebuild the frontend?

- `python app.py` builds the frontend **only if** `frontend/dist` is missing
  (first run) — never rebuilds unnecessarily.
- `python app.py --rebuild` forces a rebuild after you change the frontend.
- If Node.js is missing, NEXUS falls back to serving the frontend source
  directly so the app still works — install Node.js later and run `--rebuild`.

### Developer mode (optional)

If you are iterating on the frontend, you *can* use the Vite dev server
(hot reload). It proxies `/api` to the running backend:

```bash
cd frontend
npm install        # once
npm run dev        # http://localhost:5173
```

This is **optional** — for everyday use, run `python app.py`.

---

## Architecture

```
app.py               Single entry point: build check → FastAPI → serve → open browser
frontend/            Custom HTML/CSS/JS SPA (AI command-center UI)
  index.html         App shell (login + layout + page containers)
  src/js/            UI, API client, page renderers, particle background
  src/pages/         Per-page HTML templates loaded at runtime
  dist/              Production build served by FastAPI (generated)
backend/             FastAPI application
  app/
    api/             HTTP routers (auth, dashboard, agents, analytics, ...)
    agents/          Multi-agent fleet (data, analytics, finance, security, ...)
    ai/              AI service layer + RAG pipeline + vector store
    core/            Config, security (JWT/RBAC), audit logging
    database/        SQLAlchemy engine + sessions
    models/          SQLAlchemy ORM models
    services/        Orchestrator + demo-data generator
docker/              Dockerfiles + docker-compose (optional)
```

## Environment Variables

See `backend/.env.example`. Key ones:

| Variable          | Purpose                                   | Default               |
| ----------------- | ----------------------------------------- | --------------------- |
| `DATABASE_URL`    | SQLAlchemy URL (SQLite/PostgreSQL)        | SQLite `backend/nexus.db` |
| `SECRET_KEY`      | JWT signing secret (change in production) | dev-only value        |
| `OPENAI_API_KEY`  | Enables real LLM + embeddings             | empty → demo mode     |
| `DEMO_MODE`       | Seed/allow synthetic data                 | `true`                |
| `CORS_ORIGINS`    | Allowed origins (dev frontends)           | localhost trio        |
| `PORT`            | Server port for `python app.py`           | `8000`                |
| `NEXUS_NO_BROWSER`| Set to `1` to disable auto-open           | off                   |

Secrets are never exposed to frontend JavaScript.

## Feature Map

- **AI Command Center** — natural-language queries dispatched to specialized agents, evidence + root cause + recommendations.
- **Business Analytics** — filtered metrics, comparison, CSV export, AI chart explanations grounded in displayed data.
- **Agents** — fleet status, run history, success rates.
- **Security Center** — security score, severity distribution, event table (clearly labeled demo telemetry).
- **Operations Center** — CPU/memory/disk/latency/request/error telemetry per service.
- **Incident Management** — full lifecycle: create, assign, note, resolve, timeline.
- **Knowledge / RAG** — upload PDF/TXT/Markdown, chunked + embedded, retrieval with source citations.
- **Reports** — daily/weekly/security/operations/incident reports with export.
- **Human Approval** — manager-gated approval flows for sensitive actions, fully audited.
- **RBAC** — ADMIN / MANAGER / ANALYST / VIEWER enforced by backend dependencies.

## Testing

```bash
backend\.venv\Scripts\python -m pytest -q
```

## Deployment Notes

- Set a real `SECRET_KEY`, `OPENAI_API_KEY`, and Postgres credentials.
- `python app.py` is production-ready as-is (build + serve + API in one process).
- Run under a process manager (systemd / Docker) — see `docker/`.
- **Streamlit Cloud:** deploy the FastAPI backend separately and serve the
  `frontend/dist` build as static assets; the custom frontend remains the
  primary UI. A Streamlit adapter (if ever added) is separate and never replaces
  the main architecture.

## Roadmap / In Progress

- pgvector-backed retrieval for production-scale RAG
- Live infrastructure / security integrations
- Approvals UI in the frontend (backend endpoints already exist)