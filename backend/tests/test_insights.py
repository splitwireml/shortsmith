"""S3 Insights page data and lesson switches (L3).

Interface choices where docs/02-architecture.md is silent: a video row's numbers come from its
latest snapshot (highest checkpoint); only published videos are listed; all of the recipe's lessons
are listed, switched-off ones too, so they can be switched back on. PUT /lessons/{id} takes
`{"active": bool}` and returns the lesson.
"""

from datetime import UTC, datetime, timedelta

from pytest import approx

from app.models import CostEvent, Lesson, Snapshot, Video
from test_engine import make_pipeline


def add(session, *rows):
    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def test_insights_lists_lessons_and_video_numbers_and_lessons_can_be_switched_off(client, session):
    now = datetime.now(UTC)
    cats, dogs = make_pipeline(session), make_pipeline(session, name="Dogs")
    hit, fresh, _ = add(
        session,
        Video(pipeline_id=cats.id, status="published", title="Hit", youtube_id="yt-hit",
              published_at=now - timedelta(days=4)),
        Video(pipeline_id=cats.id, status="published", title="Fresh", youtube_id="yt-fresh",
              published_at=now - timedelta(hours=2)),
        Video(pipeline_id=cats.id, status="awaiting_approval", title="Draft"),
    )
    add(session,
        Snapshot(video_id=hit.id, checkpoint_hours=24, views=100, likes=5, comments=1),
        Snapshot(video_id=hit.id, checkpoint_hours=72, views=250, likes=9, comments=2,
                 avg_view_percent=55.0),
        Snapshot(video_id=fresh.id, checkpoint_hours=1, views=10, likes=1, comments=0),
        CostEvent(stage="video", model="gemini-omni-1.2-flash", cost_usd=0.50, video_id=hit.id,
                  pipeline_id=cats.id, unit_kind="video_seconds", reason="Clips"),
        CostEvent(stage="review", model="gemini-4-argon", cost_usd=0.25, video_id=hit.id,
                  pipeline_id=cats.id, reason="Review"))
    on, off, _ = add(session,
                     Lesson(pipeline_id=cats.id, text="ON", source="you"),
                     Lesson(pipeline_id=cats.id, text="OFF", source="analytics", active=False),
                     Lesson(pipeline_id=dogs.id, text="DOGS", source="you"))

    page = client.get("/api/insights", params={"pipeline_id": cats.id})
    assert page.status_code == 200, page.text
    assert {row["text"]: row["active"] for row in page.json()["lessons"]} == {"ON": True, "OFF": False}
    rows = {row["id"]: row for row in page.json()["videos"]}
    assert set(rows) == {hit.id, fresh.id}  # the draft has no numbers yet
    keys = ("title", "views", "likes", "comments", "avg_view_percent")
    assert {k: rows[hit.id][k] for k in keys} == {
        "title": "Hit", "views": 250, "likes": 9, "comments": 2, "avg_view_percent": 55.0}
    assert {k: rows[fresh.id][k] for k in keys} == {
        "title": "Fresh", "views": 10, "likes": 1, "comments": 0, "avg_view_percent": None}
    assert rows[hit.id]["cost_usd"] == approx(0.75) and rows[fresh.id]["cost_usd"] == 0
    assert rows[hit.id]["published_at"]

    switched = client.put(f"/api/lessons/{on.id}", json={"active": False})
    assert switched.status_code == 200, switched.text
    assert switched.json()["active"] is False
    assert client.delete(f"/api/lessons/{off.id}").is_success
    after = client.get("/api/insights", params={"pipeline_id": cats.id}).json()["lessons"]
    assert [(row["text"], row["active"]) for row in after] == [("ON", False)]
    missing = client.delete("/api/lessons/999")
    assert missing.status_code == 404 and isinstance(missing.json()["detail"], str)


def test_turning_a_lesson_back_on_needs_a_free_slot(client, session):
    # Review S3 #8: ten active is the cap, however a lesson is switched on.
    cats = make_pipeline(session)
    add(session, *[Lesson(pipeline_id=cats.id, text=f"ON-{i}", source="you") for i in range(10)])
    off, = add(session, Lesson(pipeline_id=cats.id, text="OFF", source="you", active=False))

    refused = client.put(f"/api/lessons/{off.id}", json={"active": True})
    assert refused.status_code == 422 and "Ten lessons" in refused.json()["detail"]
    session.expire_all()
    assert session.get(Lesson, off.id).active is False
