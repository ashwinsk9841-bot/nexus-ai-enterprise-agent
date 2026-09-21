"""
NEXUS — single-command entry point.

    python app.py              (classic: FastAPI serves SPA, opens browser)
    streamlit run app.py       (Streamlit host: backend auto-starts in-thread,
                                NEXUS UI embedded full-screen)

Both forms start the FastAPI backend, serve the built frontend from the same
process, build the frontend automatically if needed, and auto-initialize the
database. No second terminal is required. No `uvicorn ...` or `npm run dev`
needed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"

DEMO_HINT = (
    "Demo login: demo@nexus.io / demo1234  (manager@nexus.io / manager123, "
    "analyst@nexus.io / analyst123, viewer@nexus.io / viewer123)"
)


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


def _in_streamlit() -> bool:
    """True when this file is executed via `streamlit run app.py`."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        from streamlit.runtime import exists as st_runtime_exists
        return st_runtime_exists() and get_script_run_ctx() is not None
    except Exception:
        return False


def _find_free_port(preferred: int) -> int:
    """Return `preferred` if bindable, else an arbitrary free local port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


_NEXUS_SERVER = None
_NEXUS_SERVER_LOCK = threading.Lock()


def get_or_start_backend(fastapi_app, host: str, port: int) -> int:
    """Start the FastAPI backend once per process; return the bound port.

    Streamlit re-runs the script on every interaction, so a module-level
    singleton (guarded by a lock) prevents multiple server instances.
    Returns the port actually in use.
    """
    global _NEXUS_SERVER
    with _NEXUS_SERVER_LOCK:
        if _NEXUS_SERVER is not None:
            return _NEXUS_SERVER["port"]
        port = _find_free_port(port)
        import uvicorn

        config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        _NEXUS_SERVER = {"server": server, "thread": thread, "port": port}
        return port


def _wait_for_backend(url: str, timeout: float = 45.0) -> bool:
    """Block until the backend /api/health is answering (or timeout elapses)."""
    import time
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _run_streamlit(url: str) -> None:
    """Streamlit host: embed the NEXUS SPA full-screen in a dark page.

    The SPA is loaded in a plain (non-sandboxed) iframe pointing at the
    backend origin (http://127.0.0.1:<port>), so auth tokens stored in that
    origin's localStorage work exactly as they do in a normal browser tab.
    """
    import streamlit as st

    st.set_page_config(page_title="NEXUS", layout="wide", initial_sidebar_state="collapsed")

    st.markdown(
        """
        <style>
          [data-testid="stHeader"], [data-testid="stToolbar"],
          [data-testid="stDecoration"], [data-testid="stStatusWidget"],
          [data-testid="stSidebar"], header, footer, #MainMenu,
          [data-testid="stBottom"] { display: none !important; }
          [data-testid="stAppViewContainer"],
          [data-testid="stMain"], [data-testid="stBlockContainer"],
          [data-testid="stApp"] { background: #05060a !important; }
          [data-testid="stMain"], [data-testid="stBlockContainer"] {
            padding: 0 !important;
            max-width: 100% !important;
            width: 100% !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not _wait_for_backend(url):
        st.error(
            "NEXUS backend failed to start. Check the terminal for the uvicorn log, "
            "then re-run:  streamlit run app.py"
        )
        st.stop()

    st.markdown(
        f'<iframe src="{url}" title="NEXUS" style="position:fixed;inset:0;'
        f'width:100vw;height:100vh;border:0;background:#05060a;"></iframe>',
        unsafe_allow_html=True,
    )


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
    load_env_file(BACKEND_DIR / ".env")

    # Zero-config default: local SQLite demo database unless explicitly configured.
    os.environ.setdefault(
        "DATABASE_URL", "sqlite:///" + (BACKEND_DIR / "nexus.db").as_posix()
    )
    os.environ.setdefault("DEMO_MODE", "true")

    ensure_python_deps()

    force = "--rebuild" in sys.argv
    static_dir = ensure_frontend_build(force=force)

    host = os.environ.get("NEXUS_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT") or os.environ.get("NEXUS_PORT") or "8000")

    # Import must happen after env vars are set so config picks them up.
    sys.path.insert(0, str(BACKEND_DIR))
    from app.main import app as fastapi_app

    mount_frontend(fastapi_app, static_dir)

    if _in_streamlit():
        port = get_or_start_backend(fastapi_app, host, port)
        url = f"http://{host}:{port}"
        log(f"NEXUS backend running at {url} (embedded in Streamlit)")
        log("Use the in-page NEXUS UI to log in; close this Streamlit window to stop.")
        log(DEMO_HINT)
        _run_streamlit(url)
        return

    url = f"http://{host}:{port}"
    no_browser = os.environ.get("NEXUS_NO_BROWSER", "0").lower() in ("1", "true", "yes")

    log(f"Starting NEXUS at {url}")
    log("Frontend and backend are served by this single process. Press Ctrl+C to stop.")
    log(DEMO_HINT)
    run_server(fastapi_app, host, port, url, open_browser=not no_browser)


if __name__ == "__main__":
    main()