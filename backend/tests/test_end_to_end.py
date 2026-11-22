"""S5: one practice video, start to finish, through the HTTP API and the worker loop's own steps.

Nothing is faked except the text agents (scripted, tests/fakes.py): media and the YouTube upload
run their real practice paths, so no network and no money. The worker is driven through
`scheduler.tick` — the very function the loop calls — never by sleeping.
"""

from pytest import approx
from sqlmodel import Session

from app import scheduler
from conftest import call
from fakes import PLAN, fake_text_agents


def tick(client) -> None:
    with Session(client.app.state.engine) as session:
        call(scheduler.tick, session, client.app.state.config)


def test_practice_video_from_preset_to_published(client):
    assert client.get("/api/status").json()["practice_mode"] is True  # the default (V5)
    [animals] = [p for p in client.get("/api/presets").json() if p["name"] == "Animals"]
    recipe = client.post("/api/pipelines", json=animals)
    assert recipe.status_code == 201, recipe.text
    pid = recipe.json()["id"]
    # A test video always waits for a person, whatever the preset's approval mode (P4).
    [queued] = client.post(f"/api/pipelines/{pid}/run", json={"count": 1, "is_test": True}).json()
    vid = queued["id"]

    with fake_text_agents() as calls:
        tick(client)
        waiting = client.get("/api/videos", params={"status": "awaiting_approval"}).json()
        assert [v["id"] for v in waiting] == [vid], client.get(f"/api/videos/{vid}").json()["error"]

        approved = client.post(f"/api/videos/{vid}/approve")
        assert approved.status_code == 200, approved.text
        tick(client)

    assert (len(calls["planner"]), len(calls["reviewer"])) == (1, 1)
    page = client.get(f"/api/videos/{vid}").json()
    assert page["status"] == "published", page["error"]
    assert page["youtube_id"].startswith("practice-")
    assert page["published_at"] and page["title"] == PLAN["title"]

    # C4: the video page lists every paid step; practice media is $0, text agents are priced.
    events = page["cost_events"]
    assert {e["stage"] for e in events} == {"planning", "thumbnail", "video", "review"}
    assert all(e["cost_usd"] == 0 for e in events if e["stage"] in ("video", "thumbnail"))
    assert all(e["cost_usd"] > 0 for e in events if e["stage"] in ("planning", "review"))
    assert client.get("/api/costs/events", params={"video_id": vid}).json() == events

    # C2: the costs summary carries the same money for this video.
    spent = sum(e["cost_usd"] for e in events)
    summary = client.get("/api/costs/summary").json()
    assert [v["usd"] for v in summary["by_video"] if v["video_id"] == vid] == [approx(spent)]
    assert summary["total_usd"] == approx(spent)
    assert summary["by_stage"]["review"] == approx(
        sum(e["cost_usd"] for e in events if e["stage"] == "review"))
