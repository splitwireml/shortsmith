import json
import re
import shutil
from collections import namedtuple

from fastapi.testclient import TestClient
from sqlmodel import select

from app.main import create_app
from app.models import Settings
from conftest import FAKE_GEMINI_KEY, make_config

PIPELINE = {
    "name": "Space facts", "niche": "astronomy", "objective": "grow subscribers",
    "audience": "curious teens", "region_notes": "", "genre": "educational",
    "art_style": "bold cartoon", "target_seconds": 30, "every_days": 2, "videos_per_run": 1,
    "approval_mode": "manual", "auto_approve_score": 8, "visibility": "private", "extra_notes": "",
}
DEFAULT_SETTINGS = {
    "monthly_budget_usd": 30, "per_video_cap_usd": 6, "retention_days": 14, "max_storage_gb": 5,
    "practice_mode": True, "onboarding_done": False,
    "planner_model": "gemini-4-hydrogen", "planner_effort": "high",
    "reviewer_model": "gemini-4-argon", "reviewer_effort": "high",
    "analyst_model": "gemini-4-hydrogen", "analyst_effort": "medium",
    "helper_model": "gemini-4-hydrogen", "helper_effort": "low",
    "video_model": "gemini-omni-1.2-flash", "video_resolution": "720p",
    "image_model": "gemini-nano-banana-2.1",
}


def test_pipeline_crud(client):
    created = client.post("/api/pipelines", json=PIPELINE)
    assert created.is_success, created.text
    pipeline = created.json()
    pid = pipeline["id"]
    assert {k: pipeline[k] for k in PIPELINE} == PIPELINE
    assert (pipeline["active"], pipeline["last_run_at"]) == (True, None)
    assert [p["id"] for p in client.get("/api/pipelines").json()] == [pid]
    assert client.get(f"/api/pipelines/{pid}").json()["name"] == "Space facts"

    # The UI sends back what it loaded; read-only fields (id, created_at…) are ignored.
    paused = client.put(f"/api/pipelines/{pid}", json={**pipeline, "active": False, "every_days": 3})
    assert paused.status_code == 200, paused.text
    assert (paused.json()["active"], paused.json()["every_days"]) == (False, 3)
    assert client.get(f"/api/pipelines/{pid}").json()["active"] is False

    assert client.delete(f"/api/pipelines/{pid}").is_success
    missing = client.get(f"/api/pipelines/{pid}")
    assert missing.status_code == 404
    assert isinstance(missing.json()["detail"], str)
    assert client.put(f"/api/pipelines/{pid}", json=PIPELINE).status_code == 404
    assert client.get("/api/pipelines").json() == []

    assert client.post("/api/pipelines", json={**PIPELINE, "target_seconds": 5}).status_code == 422  # P1: 15–60 s


def test_presets_fill_every_field_and_save_as_is(client):
    # Doc is silent on shape: a list of pipeline-form dicts whose `name` is the preset name.
    # "Blank" is the empty form, not a preset.
    presets = client.get("/api/presets").json()
    assert {"Educational", "Animals", "Comedy", "Motivation", "Facts"} <= {p["name"] for p in presets}
    for preset in presets:
        assert PIPELINE.keys() <= preset.keys(), preset["name"]
        assert all(preset[k] for k in ("niche", "objective", "audience", "genre", "art_style"))
        assert 15 <= preset["target_seconds"] <= 60
        assert preset["approval_mode"] in ("manual", "auto")
        assert preset["visibility"] in ("private", "unlisted", "public")
        saved = client.post("/api/pipelines", json=preset)
        assert saved.is_success, saved.text
        assert {k: saved.json()[k] for k in PIPELINE} == {k: preset[k] for k in PIPELINE}


def test_settings_defaults_and_round_trip(client, session):
    current = client.get("/api/settings").json()
    assert {k: current[k] for k in DEFAULT_SETTINGS} == DEFAULT_SETTINGS

    edits = {"monthly_budget_usd": 50, "practice_mode": False, "planner_effort": "medium",
             "onboarding_done": True}
    saved = client.put("/api/settings", json={**current, **edits})
    assert saved.status_code == 200, saved.text
    assert {k: saved.json()[k] for k in edits} == edits
    assert client.get("/api/settings").json() == saved.json()
    assert len(session.exec(select(Settings)).all()) == 1  # exactly one row


def test_status_reports_each_check(client, monkeypatch):
    monkeypatch.setattr("app.media.check_key", lambda config: True)  # no network in tests
    status = client.get("/api/status").json()
    checks = {c["name"]: c for c in status["checks"]}
    # Doc is silent on check names; these are the four in H2.
    assert set(checks) == {"gemini", "youtube", "ffmpeg", "disk"}
    for check in checks.values():
        assert isinstance(check["ok"], bool) and check["message"]
    assert checks["gemini"]["ok"] is True  # the (patched) live key check passed
    assert checks["youtube"]["ok"] is False  # no token in the temp data folder
    assert (status["onboarding_done"], status["practice_mode"]) == (False, True)


def test_status_says_when_the_key_could_not_be_checked(client, monkeypatch):
    monkeypatch.setattr("app.media.check_key", lambda config: None)  # Google did not answer
    checks = {c["name"]: c for c in client.get("/api/status").json()["checks"]}
    assert checks["gemini"]["ok"] is False
    assert "could not check" in checks["gemini"]["message"].lower()


def test_status_explains_what_is_broken(tmp_path, monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr("app.media.check_key", lambda config: False)  # no network in tests
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(10**12, 10**12 - 10**8, 10**8))
    with TestClient(create_app(make_config(tmp_path, gemini_api_key=""))) as client:
        checks = {c["name"]: c for c in client.get("/api/status").json()["checks"]}
    for name in ("gemini", "ffmpeg", "disk"):  # no key, no ffmpeg, 100 MB free
        assert checks[name]["ok"] is False, name
        assert checks[name]["message"], name


def test_no_secret_in_any_response(config, monkeypatch):
    monkeypatch.setattr("app.media.check_key", lambda config: True)  # /status must not call out
    token_secret = "test-refresh-token-must-never-leak"
    (config.data_dir / "youtube_token.json").write_text(
        json.dumps({"token": token_secret, "refresh_token": token_secret}))
    # Server errors stay loud: a broken route must fail here, not pass
    # as a harmless empty page. The seeds below give id / key "1" to
    # every GET that takes one: pipeline 1, video 1, media file "1".
    config.media_dir.mkdir(parents=True, exist_ok=True)
    (config.media_dir / "1").write_bytes(b"x")
    with TestClient(create_app(config)) as c:
        assert c.post("/api/pipelines", json=PIPELINE).is_success
        assert c.post("/api/pipelines/1/run", json={"count": 1}).is_success
        responses = [c.put("/api/settings", json=c.get("/api/settings").json())]
        # Every GET route, today's and future sprints'. Enumerated via OpenAPI:
        # FastAPI 0.165 keeps included routers un-flattened in app.routes.
        for path, ops in c.get("/openapi.json").json()["paths"].items():
            if "get" in ops:
                responses.append(c.get(re.sub(r"\{[^}]+\}", "1", path)))
    assert len(responses) >= 7
    for r in responses:
        assert r.status_code == 200, f"{r.request.method} {r.request.url}: {r.text}"
        assert FAKE_GEMINI_KEY not in r.text, r.request.url
        assert token_secret not in r.text, r.request.url
