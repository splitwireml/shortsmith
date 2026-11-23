"""S3 YouTube: publish exactly once (Y2), an upload cut off by a restart, an expired sign-in (Y3).

Google is never reached. Interface choices where docs/02-architecture.md is silent:
- Publishing is the `approved` stage of `pipeline.advance`. It calls
  `youtube.upload(config, *, video_path, title, description, tags, privacy) -> str`
  (a plain sync function, run in a thread; "not connected" is upload's error to raise),
  commits the returned id as `published`, and only then calls the best-effort
  `youtube.set_thumbnail(config, youtube_id, thumbnail_path) -> str | None` (review S3 #1).
- The start-up check for videos left in `publishing` runs whenever the app starts, even with the
  worker loop off (`Config.run_worker=False`, see conftest).
- `youtube.SCOPES` keeps the scopes of scripts/youtube_connect.py; the token is
  `config.youtube_token_path`.
"""

import asyncio
import json
from pathlib import Path

import google.oauth2.credentials
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
from sqlmodel import Session

from app import pipeline, youtube
from app.db import get_settings
from app.main import create_app
from app.models import Video
from app.storage import Storage
from fakes import PLAN, fake_text_agents
from test_engine import advance_until_rest, make_pipeline, queue_video

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
# The shape google-auth saves after sign-in, with made-up values and an access token long expired.
EXPIRED_TOKEN = {
    "token": "fake-access-token",
    "refresh_token": "fake-refresh-token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "fake-client.apps.googleusercontent.com",
    "client_secret": "fake-client-secret",
    "scopes": SCOPES,
    "expiry": "2026-01-01T00:00:00Z",
}


def test_publish_uploads_once_and_stores_the_youtube_id(session, config, monkeypatch):
    settings = get_settings(session)
    settings.practice_mode = False  # the real path; the fake below is its only way out
    session.add(settings)
    session.commit()
    recipe = make_pipeline(session, visibility="unlisted")
    video = Video(pipeline_id=recipe.id, status="approved", title=PLAN["title"], plan=PLAN)
    session.add(video)
    session.commit()
    session.refresh(video)
    storage = Storage(config.media_dir)
    storage.put(f"videos/{video.id}/final.mp4", b"final-video")
    storage.put(f"videos/{video.id}/thumb.png", b"thumb-png")
    uploads, saved_status, thumbnails, saved_at_thumbnail = [], [], [], []

    def upload(config_, **kw):
        with Session(session.get_bind()) as other:  # what a crash mid-upload would leave behind
            saved_status.append(other.get(Video, video.id).status)
        uploads.append(kw)
        return "yt-first-upload"

    def set_thumbnail(config_, youtube_id, thumbnail_path):
        # The id must already be saved as published before thumbnail work
        # starts, so a restart here never loses a video YouTube has.
        with Session(session.get_bind()) as other:
            row = other.get(Video, video.id)
            saved_at_thumbnail.append((row.status, row.youtube_id))
        thumbnails.append((youtube_id, thumbnail_path))
        return None

    monkeypatch.setattr(youtube, "upload", upload)
    monkeypatch.setattr(youtube, "set_thumbnail", set_thumbnail)

    asyncio.run(pipeline.advance(session, video, config))

    session.refresh(video)
    assert (video.status, video.youtube_id) == ("published", "yt-first-upload"), video.error
    assert video.published_at is not None
    assert saved_status == ["publishing"]  # the lock is committed before any byte is sent
    assert saved_at_thumbnail == [("published", "yt-first-upload")]
    [sent] = uploads
    assert Path(sent["video_path"]).read_bytes() == b"final-video"
    [(thumb_id, thumb_path)] = thumbnails
    assert thumb_id == "yt-first-upload"
    assert Path(thumb_path).read_bytes() == b"thumb-png"
    assert (sent["title"], sent["tags"], sent["privacy"]) == (PLAN["title"], PLAN["tags"], "unlisted")
    assert PLAN["description"] in sent["description"]

    # Never twice: not when advanced again, not when sent back to `approved` with the id
    # already stored, and not while a video holds the `publishing` lock.
    asyncio.run(pipeline.advance(session, video, config))
    video.status = "approved"
    session.add(video)
    session.commit()
    asyncio.run(pipeline.advance(session, video, config))
    session.refresh(video)
    assert (video.status, video.youtube_id) == ("published", "yt-first-upload"), video.error
    locked = Video(pipeline_id=recipe.id, status="publishing", title="Mid-upload", plan=PLAN)
    session.add(locked)
    session.commit()
    session.refresh(locked)
    asyncio.run(pipeline.advance(session, locked, config))
    assert len(uploads) == 1


def test_a_video_left_publishing_at_start_up_fails_with_check_your_channel(session, config):
    recipe = make_pipeline(session)
    stuck = Video(pipeline_id=recipe.id, status="publishing", title="Cut off mid-upload")
    session.add(stuck)
    session.commit()
    session.refresh(stuck)

    with TestClient(create_app(config)) as client:
        page = client.get(f"/api/videos/{stuck.id}").json()
        # failed_status is `approved`: `publishing` is a lock, not a stage, so Retry re-enters publish.
        assert (page["status"], page["failed_status"]) == ("failed", "approved")
        assert "Check your YouTube channel" in page["error"]
        assert client.post(f"/api/videos/{stuck.id}/retry").json()["status"] == "approved"


def test_an_expired_google_sign_in_means_needs_reconnect(client, config, monkeypatch):
    assert youtube.SCOPES == SCOPES
    never = {"connected": False, "channel_title": None, "needs_reconnect": False}
    assert client.get("/api/youtube/status").json() == never

    config.youtube_token_path.write_text(json.dumps(EXPIRED_TOKEN))

    def refused(self, request):  # what Google answers once a "Testing" app's 7 days are up
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(google.oauth2.credentials.Credentials, "refresh", refused)

    status = client.get("/api/youtube/status")
    assert status.status_code == 200, status.text  # a plain answer, never a crash
    assert status.json() == {"connected": False, "channel_title": None, "needs_reconnect": True}

    # Disconnect forgets the dead sign-in, so the page offers a fresh Connect.
    assert client.post("/api/youtube/disconnect").is_success
    assert not config.youtube_token_path.exists()
    assert client.get("/api/youtube/status").json() == never


def test_fetch_stats_keeps_the_counts_when_analytics_fails(config, monkeypatch):
    # Review S3 #4: Analytics is a bonus — its failure must not throw
    # away views/likes/comments the Data API already gave us.
    class _Request:
        def __init__(self, payload=None, error=None):
            self.payload, self.error = payload, error

        def execute(self):
            if self.error:
                raise self.error
            return self.payload

    class _Data:
        def videos(self):
            return self

        def list(self, **_kw):
            return _Request({"items": [{"statistics": {
                "viewCount": "42", "likeCount": "7", "commentCount": "3"}}]})

    class _Analytics:
        def reports(self):
            return self

        def query(self, **_kw):
            return _Request(error=RuntimeError("analytics unavailable"))

    monkeypatch.setattr(youtube, "_load_credentials", lambda _config: object())
    monkeypatch.setattr(
        youtube, "build", lambda service, *_a, **_kw: _Data() if service == "youtube" else _Analytics()
    )

    assert youtube.fetch_stats(config, "yt-x", with_analytics=True) == {
        "views": 42, "likes": 7, "comments": 3}


def test_a_practice_video_approved_after_practice_mode_is_off_never_reaches_youtube(
    client, session, config, monkeypatch
):
    video = queue_video(session, make_pipeline(session))
    with fake_text_agents():
        advance_until_rest(session, video, config)  # made from free coloured practice clips
    assert video.status == "awaiting_approval", video.error

    settings = get_settings(session)
    settings.practice_mode = False  # the owner switches practice off, then approves the old video
    session.add(settings)
    session.commit()
    real_upload, sent_for_real = youtube.upload, []

    def upload(config_, **kw):
        if not kw.get("practice"):
            sent_for_real.append(kw["title"])
            return "yt-real-upload"
        return real_upload(config_, **kw)  # the practice path: a fake id, no network

    monkeypatch.setattr(youtube, "upload", upload)
    monkeypatch.setattr(youtube, "set_thumbnail", lambda *args: None)

    assert client.post(f"/api/videos/{video.id}/approve").status_code == 200
    session.refresh(video)
    asyncio.run(pipeline.advance(session, video, config))

    session.refresh(video)
    assert sent_for_real == []
    assert video.status == "published", video.error
    assert video.youtube_id.startswith("practice-")
