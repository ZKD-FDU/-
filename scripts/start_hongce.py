"""One-command local launcher for HongCe."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"


def main() -> int:
    python = sys.executable
    host = os.environ.get("HONGCE_HOST", "127.0.0.1")
    api_host = os.environ.get("HONGCE_API_HOST", host)
    api_port = int(os.environ.get("HONGCE_API_PORT", "8000"))
    web_host = os.environ.get("HONGCE_WEB_HOST", host)
    web_port = int(os.environ.get("HONGCE_WEB_PORT", "5173"))
    public_api_base = os.environ.get("HONGCE_PUBLIC_API_BASE", f"http://127.0.0.1:{api_port}")
    web_url = f"http://127.0.0.1:{web_port}"

    ensure_runtime()
    write_web_config(public_api_base)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["HONGCE_API_HOST"] = api_host
    env["HONGCE_API_PORT"] = str(api_port)

    api = subprocess.Popen([python, "-m", "api.simple_server"], cwd=ROOT, env=env)
    web = subprocess.Popen([python, "-m", "http.server", str(web_port), "--bind", web_host], cwd=WEB_DIR)
    children = [api, web]

    try:
        wait_for(f"http://127.0.0.1:{api_port}/health", "API")
        wait_for(web_url, "frontend")
        print()
        print(f"HongCe is running: {web_url}")
        print("Press Ctrl+C here to stop both services.")
        webbrowser.open(web_url)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        return next((child.returncode for child in children if child.returncode), 0)
    except KeyboardInterrupt:
        print("\nStopping HongCe services...")
        return 0
    finally:
        for child in children:
            stop(child)


def ensure_runtime() -> None:
    try:
        import pydantic  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: pydantic. Install it first with `python3 -m pip install pydantic`."
        ) from exc


def write_web_config(api_base: str) -> None:
    config = WEB_DIR / "hongce-config.js"
    config.write_text(
        f'window.HONGCE_API_BASE = "{api_base.rstrip("/")}";\n',
        encoding="utf-8",
    )


def wait_for(url: str, label: str) -> None:
    deadline = time.time() + 15
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"{label} did not become ready at {url}: {last_error}")


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
