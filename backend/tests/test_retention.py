"""S3 clean-up (S2): old media is deleted, database rows are kept.

Interface choice where docs/02-architecture.md is silent: `retention.clean(session, config, now=)`
does the clean-up; running it at most once a day is the worker loop's job. The size cap counts
media (`Storage.size`), not the database. A video still on its way to YouTube (`approved`) keeps
its file whatever its age.
"""

from datetime import UTC, datetime, timedelta

from app import retention
from app.db import get_settings
from app.models import Video
from app.storage import Storage
from conftest import call
from test_engine import make_pipeline


def make(session, storage: Storage, status: str, days_old: float, *, bytes_each: int = 10,
         published_days_ago: float | None = None) -> Video:
    now = datetime.now(UTC)
    recipe = make_pipeline(session)
    video = Video(pipeline_id=recipe.id, status=status, title=f"{status} {days_old} days",
                  created_at=now - timedelta(days=days_old))
    if published_days_ago is not None:
        video.youtube_id = f"yt-{days_old}"
        video.published_at = now - timedelta(days=published_days_ago)
    session.add(video)
    session.commit()
    session.refresh(video)
    for name in ("clip_0.mp4", "final.mp4", "thumb.png"):
        storage.put(f"videos/{video.id}/{name}", b"x" * bytes_each)
    return video


def outcome(session, storage: Storage, video: Video) -> tuple[str, bool, bool]:
    """(status, media still on disk, media_deleted_at set); the row itself must survive."""
    session.expire_all()
    row = session.get(Video, video.id)
    return row.status, bool(storage.list(f"videos/{video.id}/")), row.media_deleted_at is not None


def test_clean_up_by_age(session, config):  # Settings default: keep 14 days
    storage = Storage(config.media_dir)
    old_rejected = make(session, storage, "rejected", 20)
    old_failed = make(session, storage, "failed", 20)
    young_rejected = make(session, storage, "rejected", 3)
    old_published = make(session, storage, "published", 30, published_days_ago=20)
    young_published = make(session, storage, "published", 3, published_days_ago=2)
    old_approved = make(session, storage, "approved", 20)  # waiting to upload: needs its file

    call(retention.clean, session, config, now=datetime.now(UTC))

    assert outcome(session, storage, old_rejected) == ("archived", False, True)
    assert outcome(session, storage, old_failed) == ("archived", False, True)
    assert outcome(session, storage, old_published) == ("published", False, True)  # stays on YouTube
    assert outcome(session, storage, young_rejected) == ("rejected", True, False)
    assert outcome(session, storage, young_published) == ("published", True, False)
    assert outcome(session, storage, old_approved) == ("approved", True, False)


def test_clean_up_by_size_deletes_the_oldest_first(session, config):
    settings = get_settings(session)
    # Three videos of ~3 kB are over the cap, two are under, whether a GB is 10^9 or 2^30 bytes.
    settings.max_storage_gb = 7500 / 1e9
    session.add(settings)
    session.commit()
    storage = Storage(config.media_dir)
    oldest = make(session, storage, "published", 3, bytes_each=1000, published_days_ago=3)
    middle = make(session, storage, "published", 2, bytes_each=1000, published_days_ago=2)
    newest = make(session, storage, "published", 1, bytes_each=1000, published_days_ago=1)

    call(retention.clean, session, config, now=datetime.now(UTC))

    assert outcome(session, storage, oldest) == ("published", False, True)
    assert outcome(session, storage, middle) == ("published", True, False)
    assert outcome(session, storage, newest) == ("published", True, False)


def test_old_approval_drafts_age_out_too(session, config):
    # Review S3 #11: a draft nobody approved is unpublished like any other.
    storage = Storage(config.media_dir)
    old_draft = make(session, storage, "awaiting_approval", 20)
    fresh_draft = make(session, storage, "awaiting_approval", 3)

    call(retention.clean, session, config, now=datetime.now(UTC))

    assert outcome(session, storage, old_draft) == ("archived", False, True)
    assert outcome(session, storage, fresh_draft) == ("awaiting_approval", True, False)
