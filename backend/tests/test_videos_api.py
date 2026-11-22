"""S2 video routes: the inbox, approve, reject, feedback (A1–A4).

Lessons are read from the database: their route (GET /insights) arrives in S3.
"""

from sqlmodel import select

from app.models import Lesson, Video
from test_costs import make_pipeline


def make_video(session, pipeline, status="awaiting_approval") -> Video:
    v = Video(pipeline_id=pipeline.id, status=status, title="Why cats land on their feet")
    session.add(v)
    session.commit()
    session.refresh(v)
    return v


def lessons(session) -> list[tuple]:
    session.expire_all()
    return [(l.text, l.source, l.pipeline_id, l.video_id, l.active)
            for l in session.exec(select(Lesson)).all()]


def inbox(client) -> list[int]:
    listed = client.get("/api/videos", params={"status": "awaiting_approval"})
    assert listed.status_code == 200, listed.text
    return [v["id"] for v in listed.json()]


def test_approve_from_the_inbox(client, session):
    cats = make_pipeline(session)
    waiting, queued = make_video(session, cats), make_video(session, cats, status="queued")
    assert inbox(client) == [waiting.id]

    approved = client.post(f"/api/videos/{waiting.id}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert inbox(client) == []

    # Wrong state or unknown video: a 4xx with a plain sentence, nothing changes.
    for path in (f"/api/videos/{waiting.id}/approve", f"/api/videos/{queued.id}/approve",
                 f"/api/videos/{queued.id}/retry", "/api/videos/999/approve"):
        refused = client.post(path)
        assert 400 <= refused.status_code < 500, path
        assert isinstance(refused.json()["detail"], str), path
    assert client.get(f"/api/videos/{queued.id}").json()["status"] == "queued"


def test_reject_reason_becomes_a_lesson_word_for_word(client, session):
    cats = make_pipeline(session)
    video = make_video(session, cats)
    reason = "Too dark — keep the colours bright, like the thumbnail."

    rejected = client.post(f"/api/videos/{video.id}/reject", json={"reason": reason})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert lessons(session) == [(reason, "you", cats.id, video.id, True)]

    for body in ({}, {"reason": ""}):  # the reason is optional: no reason, no lesson
        other = make_video(session, cats)
        assert client.post(f"/api/videos/{other.id}/reject", json=body).json()["status"] == "rejected"
    assert len(lessons(session)) == 1


def test_feedback_sets_the_rating_and_the_note_becomes_a_lesson(client, session):
    cats = make_pipeline(session)
    published = make_video(session, cats, status="published")
    waiting = make_video(session, cats)
    note = "The question hook worked — do more of those."

    liked = client.post(f"/api/videos/{published.id}/feedback", json={"rating": 1, "note": note})
    assert liked.status_code == 200, liked.text
    assert liked.json()["rating"] == 1
    assert lessons(session) == [(note, "you", cats.id, published.id, True)]

    # Before publishing too; a rating alone adds no lesson.
    disliked = client.post(f"/api/videos/{waiting.id}/feedback", json={"rating": -1})
    assert (disliked.json()["rating"], disliked.json()["status"]) == (-1, "awaiting_approval")
    assert len(lessons(session)) == 1
    assert client.post(f"/api/videos/{waiting.id}/feedback", json={"rating": 5}).status_code == 422
