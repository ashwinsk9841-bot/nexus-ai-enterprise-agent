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

### Previewing the Vercel behavior locally

```bash
npx vercel dev
```

Runs the same install/build pipeline as production (pip + npm build) and
serves the site through Vercel's local runtime — useful to confirm the
`app.py` entrypoint before pushing.

---

## Architecture

```
vercel.json          Vercel config: pip install → npm build → static dist + app.py function
requirements.txt     Root manifest for the Vercel Python runtime (fastapi visible)
app.py               Single entry point: local `python app.py` (uvicorn + browser)
                     and Vercel ASGI entry (module-level `app`, per-request, no port)
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
| `DATABASE_URL`    | SQLAlchemy URL (SQLite/PostgreSQL)        | SQLite `backend/nexus.db` locally; ephemeral `/tmp` SQLite on Vercel until you set a Postgres URL |
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

## Deployment — Vercel (production)

NEXUS deploys to Vercel as a FastAPI project with a static frontend:

- **Entry point:** `app.py` (module-level `app = FastAPI(...)`) — Vercel detects
  `fastapi` in `requirements.txt` and invokes this ASGI app per request.
  No port is bound, no server process is kept alive, nothing is Streamlit.
- **Frontend:** `vercel.json` builds `frontend/dist` (`npm run build`) and
  serves it statically; `/api/*` falls through to the FastAPI function.
  The function also bundles `frontend/dist` (`includeFiles`) so deep links
  (`/analytics`, `/admin`, ...) get the SPA shell even on a filesystem miss.
- **Database:** set `DATABASE_URL` to a PostgreSQL URL (Neon, Vercel Postgres,
  …). Without it, Vercel falls back to **ephemeral `/tmp` SQLite** (fine for a
  demo — every cold start re-seeds the demo users, data does not persist).
  The local default (`backend/nexus.db`) is never used on Vercel.

### Deploy steps

```bash
npm i -g vercel        # or: npx vercel
vercel login
vercel link            # choose/creates the project — name it "nexus-enterprise-agent"
vercel --prod
```

Or connect the GitHub repo in the Vercel dashboard (framework is
auto-detected; no preset override needed).

To get `https://nexus-enterprise-agent.vercel.app`, the Vercel **project
name must be** `nexus-enterprise-agent`.

### Environment variables (Vercel project → Settings → Environment Variables)

| Variable               | Required | Purpose                                        |
| ---------------------- | -------- | ---------------------------------------------- |
| `DATABASE_URL`         | **yes** (prod) | PostgreSQL URL, e.g. `postgres://…?sslmode=require` |
| `SECRET_KEY`           | **yes**  | JWT signing secret — set a long random value   |
| `OPENAI_API_KEY`       | optional | Enables real LLM + embeddings (else demo mode) |
| `DEMO_MODE`            | optional | Seed/allow synthetic demo data (default `true`) |
| `NEXUS_ADMIN_EMAIL`    | optional | Bootstrap an admin account on first run        |
| `NEXUS_ADMIN_PASSWORD_HASH` | optional | PBKDF2 hash for the bootstrapped admin    |
| `ALLOW_SIGNUP`         | optional | Public self-registration (default on)          |
| `CORS_ORIGINS`         | optional | Extra allowed origins (same-origin by default) |
| `ENVIRONMENT` / `DEBUG` / `NEXUS_AI_PROVIDER` | optional | Runtime toggles               |

There is **no email provider**: OTP / email verification / forgot-password are
intentionally not part of the system (registration is password-based).

### Serverless behavior (what differs from `python app.py`)

- **DB init runs per request, once per container** — a middleware (plus the
  lifespan, where supported) calls the idempotent `init_db()` so tables and
  demo users exist even though Vercel may never send a lifespan event.
- **In-memory rate limiter and the AI vector store are per-instance** — they
  reset on cold starts (not a shared store; swap for Redis if you need
  global limits).
- **Long AI operations** are capped by `maxDuration: "max"` in `vercel.json`;
  very long runs can still hit plan limits — re-run from the UI if so.
- **No npm/uvicorn at import time on Vercel** — guarded by the `VERCEL` env
  flag; the build happens in `buildCommand`.

## Deployment — Docker (optional, self-hosted)

- Set a real `SECRET_KEY`, `OPENAI_API_KEY`, and Postgres credentials.
- `python app.py` is production-ready as-is (build + serve + API in one process).
- Run under a process manager (systemd / Docker) — see `docker/`.

## Roadmap / In Progress

- pgvector-backed retrieval for production-scale RAG
- Live infrastructure / security integrations
- Approvals UI in the frontend (backend endpoints already exist)