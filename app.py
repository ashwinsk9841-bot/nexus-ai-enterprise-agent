"""
NEXUS — single entry point for local dev and Vercel production.

    python app.py        local: FastAPI serves the SPA + /api on one port,
                         builds the frontend if needed, opens the browser.

    Vercel               imports this module and uses the module-level
                         `app` (FastAPI) as the ASGI entrypoint. No server
                         is started, no port is bound, no process is kept
                         alive: Vercel invokes `app` per request. The
                         frontend is built by vercel.json's buildCommand
                         and served statically; /api/* falls through to
                         this ASGI app.

Both paths serve the built frontend and the /api routes from a SINGLE
origin — same URLs locally and in production.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

DEMO_HINT = (
    "Demo login: demo@nexus.io / demo1234  (manager@nexus.io / manager123, "
    "analyst@nexus.io / analyst123, viewer@nexus.io / viewer123)"
)

RUNNING_ON_VERCEL = bool(os.environ.get("VERCEL"))


def log(msg: str) -> None:
    print(f"[NEXUS] {msg}")


def load_env_file(path: Path) -> None:
    """Minimal .env loader — values already in the real environment always win."""
    if not path.is_file():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except OSError as exc:
        log(f"could not read {path}: {exc}")


def ensure_python_deps() -> None:
    try:
        import fastapi  # noqa: F401
    except ImportError:
        print(
            "\nNEXUS requires its Python dependencies.\n"
            "  pip install -r backend\\requirements.txt\n"
            "Or activate the provided virtual environment:  backend\\.venv\\Scripts\\activate\n"
        )
        sys.exit(1)


def _npm_path() -> str | None:
    npm = shutil.which("npm")
    if npm:
        return npm
    node = shutil.which("node")
    if node:
        return os.path.join(os.path.dirname(node), "npm.cmd")
    return None


def ensure_frontend_build(force: bool = False) -> Path:
    """Return the directory to serve (dist build if available, else frontend source)."""
    index = DIST_DIR / "index.html"
    if index.is_file() and not force:
        return DIST_DIR
    if RUNNING_ON_VERCEL:
        # Vercel runs `npm run build` via vercel.json's buildCommand before
        # packaging — never shell out to npm from inside a serverless import.
        log("frontend/dist missing on Vercel — check the buildCommand output.")
        return DIST_DIR if index.is_file() else FRONTEND_DIR
    if not FRONTEND_DIR.is_dir():
        sys.exit(f"[NEXUS] frontend directory not found: {FRONTEND_DIR}")

    npm = _npm_path()
    if npm is None:
        log("Node.js/npm not found — serving the frontend SOURCE directly (no build step).")
        log("For a production build, install Node.js and re-run:  python app.py --rebuild")
        return FRONTEND_DIR

    def npm_run(suffix: str, desc: str) -> None:
        log(desc)
        cmd = f'"{npm}" {suffix}'
        result = subprocess.run(cmd, cwd=str(FRONTEND_DIR), shell=True)
        if result.returncode != 0:
            sys.exit(f"[NEXUS] {desc} failed (exit {result.returncode}).")

    if not (FRONTEND_DIR / "node_modules").is_dir():
        npm_run("install", "installing frontend dependencies (first run)...")
    npm_run("run build", "building frontend production bundle...")

    if not index.is_file():
        log("Build finished but dist/index.html is missing — serving source instead.")
        return FRONTEND_DIR
    return DIST_DIR


def mount_frontend(fastapi_app, static_dir: Path) -> None:
    """Deprecated — the FastAPI app (app.main) now serves the frontend itself.

    Kept as a no-op for backwards compatibility with any external caller;
    static serving is registered inside backend/app/main.py.
    """
    return


# ---------------------------------------------------------------------------
# Module-level ASGI app — THE production entrypoint.
#
# Local:   `python app.py` runs main() below (uvicorn, browser open).
# Vercel:  imports this module and calls `app` per request (no main(), no
#          port, no background process). FastAPI framework detection reads
#          `fastapi` from requirements.txt and picks up this `app`.
# ---------------------------------------------------------------------------

def _prepare_environment() -> None:
    load_env_file(BACKEND_DIR / ".env")

    if RUNNING_ON_VERCEL:
        # Serverless filesystem is read-only (except /tmp): never point the
        # default DB at backend/nexus.db here. /tmp SQLite is an ephemeral
        # zero-config demo fallback — set DATABASE_URL (PostgreSQL) in the
        # Vercel project settings for a persistent production database.
        if not os.environ.get("DATABASE_URL"):
            os.environ["DATABASE_URL"] = "sqlite:////tmp/nexus.db"
            log(
                "DATABASE_URL is not set — using ephemeral /tmp SQLite. "
                "Set DATABASE_URL (PostgreSQL) in Vercel Environment Variables "
                "for persistent data."
            )
    else:
        # Zero-config default: local SQLite demo database unless explicitly configured.
        os.environ.setdefault(
            "DATABASE_URL", "sqlite:///" + (BACKEND_DIR / "nexus.db").as_posix()
        )
    os.environ.setdefault("DEMO_MODE", "true")


def _load_backend_module():
    """Import backend/app/main.py as `backend.app.main` (no `app` name clash)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    import backend.app.main as backend_module
    return backend_module


_prepare_environment()
ensure_python_deps()
# Best-effort auto-build so a freshly-cloned repo (no `dist/`) still serves a
# production bundle. On Vercel the build already ran (buildCommand) — see the
# guard inside ensure_frontend_build.
ensure_frontend_build(force=False)

_backend = _load_backend_module()

# ---------------------------------------------------------------------------
# Serverless-safe database initialization.
#
# Vercel invokes the ASGI app per request and may not deliver lifespan
# startup events, so init_db() runs once per container through BOTH the
# lifespan (when supported) and a request middleware (guaranteed). init_db()
# is idempotent: create_all + guarded migrations + seed-only-when-empty.
# ---------------------------------------------------------------------------
_init_lock = threading.Lock()
_db_ready = False


def _init_db_once() -> None:
    global _db_ready
    if _db_ready:
        return
    with _init_lock:
        if _db_ready:
            return
        _backend.init_db()
        _db_ready = True


@asynccontextmanager
async def _nexus_lifespan(_app: FastAPI):
    try:
        _init_db_once()
    except Exception:
        import logging
        logging.getLogger("nexus").exception(
            "Database initialization failed — check DATABASE_URL"
        )
    yield


app = FastAPI(
    title="NEXUS",
    version=getattr(_backend.app, "version", "1.0.0"),
    description="Enterprise AI Intelligence & Operations Platform",
    lifespan=_nexus_lifespan,
)


@app.middleware("http")
async def _ensure_db_initialized(request, call_next):
    # Guarantees schema + demo seed exist even if the runtime never sends a
    # lifespan event. On failure, _db_ready stays False so the next request
    # retries instead of serving 500s forever.
    if not _db_ready:
        try:
            _init_db_once()
        except Exception:
            import logging
            logging.getLogger("nexus").exception(
                "Deferred database initialization failed — check DATABASE_URL"
            )
    return await call_next(request)


app.mount("/", _backend.app)


# ---------------------------------------------------------------------------
# Classic local entry: `python app.py`
# ---------------------------------------------------------------------------

def run_server(fastapi_app, host: str, port: int, url: str, open_browser: bool) -> None:
    import uvicorn

    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
    server = _BrowserOpenServer(config, url if open_browser else None)
    try:
        server.run()
    except KeyboardInterrupt:
        log("NEXUS stopped.")
    except OSError as exc:
        sys.exit(f"[NEXUS] Could not bind {host}:{port} — is NEXUS (or another app) already running?\n{exc}")


class _BrowserOpenServer:
    """Uvicorn server that opens the browser only once, after the socket is live."""

    def __init__(self, config, url):
        import uvicorn

        self._inner = uvicorn.Server(config)
        self._url = url
        self._opened = False

    def run(self, sockets=None):
        inner = self._inner
        original_startup = inner.startup

        async def startup_with_browser(*args, **kwargs):
            await original_startup(*args, **kwargs)
            if (
                inner.started
                and not inner.should_exit
                and self._url
                and not self._opened
            ):
                self._opened = True
                threading.Thread(
                    target=webbrowser.open, args=(self._url,), daemon=True
                ).start()

        inner.startup = startup_with_browser
        return inner.run(sockets=sockets)


def main() -> None:
    force = "--rebuild" in sys.argv
    ensure_frontend_build(force=force)

    host = os.environ.get("NEXUS_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT") or os.environ.get("NEXUS_PORT") or "8000")

    url = f"http://{host}:{port}"
    no_browser = os.environ.get("NEXUS_NO_BROWSER", "0").lower() in ("1", "true", "yes")

    log(f"Starting NEXUS at {url}")
    log("Frontend and backend are served by this single process. Press Ctrl+C to stop.")
    log(DEMO_HINT)
    run_server(app, host, port, url, open_browser=not no_browser)


if __name__ == "__main__":
    main()
