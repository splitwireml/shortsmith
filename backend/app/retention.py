"""Clean-up by age and by size (S2). Database rows are always kept.

Old unpublished videos — rejected, failed, or a draft nobody ever
approved — lose their files and become `archived`; old published
videos lose only the local copies (they stay on YouTube). A video
still being made, or approved and waiting to upload, keeps its
files whatever its age. If the media folder then still exceeds the
size cap, the oldest remaining media goes first.

One pass over one folder listing: byte counts are tallied once and
reduced as files are deleted. Running this at most once a day is
the worker loop's job.
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, select

from app import db
from app.config import Config
from app.models import Video, VideoStatus
from app.storage import Storage

# Never-published states that become `archived` when their media goes.
_ARCHIVABLE = {VideoStatus.rejected, VideoStatus.failed, VideoStatus.awaiting_approval}


def _utc(moment: datetime) -> datetime:
    # SQLite hands some datetimes back without a timezone; they are UTC.
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def clean(session: Session, config: Config, now: datetime | None = None) -> None:
    now = _utc(now or datetime.now(UTC))
    settings = db.get_settings(session)
    storage = Storage(config.media_dir)
    keep = timedelta(days=settings.retention_days)

    # One listing, tallied per video; files outside a video folder
    # count toward the cap but are never deleted here.
    keys_by_video: dict[int, list[str]] = {}
    bytes_by_video: dict[int, int] = {}
    total_bytes = 0
    for key in storage.list(""):
        size = storage.path(key).stat().st_size
        total_bytes += size
        parts = key.split("/")
        if len(parts) > 2 and parts[0] == "videos" and parts[1].isdigit():
            video_id = int(parts[1])
            keys_by_video.setdefault(video_id, []).append(key)
            bytes_by_video[video_id] = bytes_by_video.get(video_id, 0) + size

    def delete_media(video: Video) -> None:
        nonlocal total_bytes
        for key in keys_by_video.pop(video.id, []):
            storage.delete(key)
        total_bytes -= bytes_by_video.pop(video.id, 0)
        video.media_deleted_at = now
        if video.status in _ARCHIVABLE:
            video.status = VideoStatus.archived
        session.add(video)

    videos = list(
        session.exec(
            select(Video).where(col(Video.media_deleted_at).is_(None)).order_by(col(Video.id))
        ).all()
    )
    for video in videos:  # by age
        if video.status == VideoStatus.published:
            basis = video.published_at or video.created_at
        elif video.status in _ARCHIVABLE:
            basis = video.created_at
        else:
            continue  # still on its way: its files are needed
        if now - _utc(basis) > keep:
            delete_media(video)

    cap_bytes = int(settings.max_storage_gb * 1_000_000_000)
    if total_bytes > cap_bytes:  # by size, oldest first
        # Drafts still waiting for their person are not size-eligible:
        # only age retires them, in the pass above.
        candidates = sorted(
            (
                v
                for v in videos
                if v.media_deleted_at is None
                and v.status != VideoStatus.awaiting_approval
                and (v.status == VideoStatus.published or v.status in _ARCHIVABLE)
                and v.id in keys_by_video
            ),
            key=lambda v: (_utc(v.created_at), v.id or 0),
        )
        for video in candidates:
            if total_bytes <= cap_bytes:
                break
            delete_media(video)
    session.commit()
