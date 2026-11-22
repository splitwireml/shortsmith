"""Start Shortsmith: `cd backend && uv run python -m app`.

This is what start.command runs. The web pages are built on the
first start (or after they are deleted), then the app is served on
127.0.0.1:8484 and opened in the browser. Opening the browser uses
the usual `webbrowser` rules, so `BROWSER=true` makes it a no-op.
"""

import shutil
import subprocess
import threading
import webbrowser

import uvicorn

from app.config import REPO_ROOT, Config
from app.main import create_app

URL = "http://127.0.0.1:8484"


def _build_frontend() -> None:
    """Build the web pages if there is no built copy yet."""
    frontend = REPO_ROOT / "frontend"
    if (frontend / "build" / "index.html").is_file():
        return
    if shutil.which("node") is None or shutil.which("pnpm") is None:
        print(
            "The app's pages still need building, but Node or pnpm was "
            "not found on this computer. Install them, then start "
            "Shortsmith again."
        )
        return
    print("Building the app's pages (first start only)…")
    for command in (["pnpm", "install", "--frozen-lockfile"], ["pnpm", "build"]):
        if subprocess.run(command, cwd=frontend).returncode != 0:
            print(
                "Building the app's pages did not finish, so Shortsmith "
                "is starting without them. Fix the messages above, then "
                "start Shortsmith again."
            )
            return


def main() -> None:
    _build_frontend()
    # The timer fires just after uvicorn starts listening below.
    threading.Timer(1.0, webbrowser.open, args=(URL,)).start()
    uvicorn.run(create_app(Config()), host="127.0.0.1", port=8484)


if __name__ == "__main__":
    main()
