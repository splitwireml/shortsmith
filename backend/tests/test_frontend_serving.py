"""S5: FastAPI serves the built SvelteKit app (adapter-static, fallback index.html).

Interface choice where docs/02-architecture.md is silent: `Config.frontend_dir` (default
`REPO_ROOT / "frontend" / "build"`) names the build folder; a missing folder means API only.
"""

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_config


def test_built_frontend_is_served_and_api_stays_json(tmp_path):
    build = tmp_path / "build"
    (build / "_app" / "immutable").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>SPA-INDEX</title>")
    (build / "_app" / "immutable" / "start.js").write_text("export const marker = 'STATIC-JS';")
    (build / "favicon.png").write_bytes(b"\x89PNG-fake-icon")

    with TestClient(create_app(make_config(tmp_path / "data", frontend_dir=build))) as c:
        # SPA fallback: any app route, even one opened directly, gets index.html.
        for path in ("/", "/videos/3", "/pipelines/new", "/settings"):
            page = c.get(path)
            assert page.status_code == 200, path
            assert page.headers["content-type"].startswith("text/html"), path
            assert "SPA-INDEX" in page.text, path

        js = c.get("/_app/immutable/start.js")
        assert js.status_code == 200 and "STATIC-JS" in js.text
        assert c.get("/favicon.png").content == b"\x89PNG-fake-icon"

        assert c.get("/api/settings").json()["practice_mode"] is True
        # An unknown API path is a JSON 404, never the app's index.html.
        for path in ("/api/nope", "/api/nope/deeper", "/api/videos/999"):
            missing = c.get(path)
            assert missing.status_code == 404, path
            assert missing.headers["content-type"].startswith("application/json"), path
            assert isinstance(missing.json()["detail"], str), path


def test_without_a_build_the_api_still_starts(tmp_path):
    config = make_config(tmp_path / "data", frontend_dir=tmp_path / "never-built")
    with TestClient(create_app(config)) as c:
        assert c.get("/api/settings").status_code == 200
