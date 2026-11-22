"""The worker loop: every 30 s, do whatever is due.

Due recipe runs queue videos, waiting videos advance one stage at a
time (oldest first, one at a time), published videos get their
snapshots at fixed checkpoints, the analyst learns at most once a
day per recipe, and clean-up runs daily. All state lives in the
database, so a laptop that slept simply catches up — a missed
checkpoint is not back-filled; one snapshot is taken, labelled with
the latest checkpoint passed.

# ponytail: one video at a time, sequentially; parallelise clips
# inside a video if speed ever matters.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app import costs, pipeline, retention, youtube
from app.agents import analyst
from app.config import Config
from app.models import (
    CostEvent,
    Lesson,
    LessonSource,
    Pipeline,
    Snapshot,
    Stage,
    Video,
    VideoStatus,
    is_on_youtube,
)

log = logging.getLogger(__name__)

CHECKPOINT_HOURS = (1, 6, 24, 48, 72, 168, 672)
MATURE_HOURS = 72  # the Analytics API only has numbers from here on
MAX_ACTIVE_LESSONS = 10
_WORKING = (
    VideoStatus.queued,
    VideoStatus.generating,
    VideoStatus.reviewing,
    VideoStatus.approved,
)
_SNAPSHOT_FIELDS = (
    "views", "likes", "comments", "avg_view_seconds", "avg_view_percent",
    "shares", "subscribers_gained",
)


def _utc(moment: datetime) -> datetime:
    # SQLite hands some datetimes back without a timezone; they are UTC.
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def create_due_videos(session: Session, now: datetime | None = None) -> None:
    """Queue `videos_per_run` for each active recipe whose turn has come.

    A recipe that never ran is due at once. `last_run_at` jumps to
    now, so a laptop asleep for a week queues one batch, not seven.
    """
    now = _utc(now or datetime.now(UTC))
    recipes = session.exec(
        select(Pipeline)
        .where(col(Pipeline.deleted_at).is_(None), col(Pipeline.active).is_(True))
        .order_by(col(Pipeline.id))
    ).all()
    for recipe in recipes:
        due = recipe.last_run_at is None or now >= _utc(recipe.last_run_at) + timedelta(
            days=recipe.every_days
        )
        if not due:
            continue
        session.add_all(
            Video(pipeline_id=recipe.id, status=VideoStatus.queued, is_test=False)
            for _ in range(recipe.videos_per_run)
        )
        recipe.last_run_at = now
        session.add(recipe)
    session.commit()


async def take_due_snapshots(
    session: Session, config: Config, now: datetime | None = None
) -> None:
    """One snapshot per published video whose next checkpoint has passed."""
    now = _utc(now or datetime.now(UTC))
    videos = session.exec(
        select(Video)
        .where(Video.status == VideoStatus.published)
        .order_by(col(Video.published_at), col(Video.id))
    ).all()
    for video in videos:
        if video.published_at is None or not is_on_youtube(video):
            continue  # practice uploads never reached YouTube (V5)
        age_hours = (now - _utc(video.published_at)).total_seconds() / 3600
        due = [c for c in CHECKPOINT_HOURS if c <= age_hours]
        if not due:
            continue
        checkpoint = max(due)
        taken = {
            s.checkpoint_hours
            for s in session.exec(select(Snapshot).where(Snapshot.video_id == video.id)).all()
        }
        if taken and max(taken) >= checkpoint:
            continue
        try:
            numbers = await asyncio.to_thread(
                youtube.fetch_stats, config, video.youtube_id,
                with_analytics=checkpoint >= MATURE_HOURS,
            )
        except Exception:  # noqa: BLE001 — one video must not stop the rest
            log.exception("Could not collect numbers for video %s", video.id)
            continue
        fields = {k: numbers[k] for k in _SNAPSHOT_FIELDS if k in numbers}
        session.add(Snapshot(video_id=video.id, checkpoint_hours=checkpoint, **fields))
        session.commit()


def _has_new_mature_snapshot(session: Session, recipe: Pipeline, since: datetime | None) -> bool:
    snaps = session.exec(
        select(Snapshot)
        .join(Video)
        .where(Video.pipeline_id == recipe.id, Snapshot.checkpoint_hours >= MATURE_HOURS)
    ).all()
    if since is None:
        return bool(snaps)
    return any(_utc(s.created_at) > _utc(since) for s in snaps)


def _apply_lessons(session: Session, recipe: Pipeline, result: analyst.Analysis) -> None:
    for lesson_id in result.lesson_ids_to_retire:
        row = session.get(Lesson, lesson_id)
        if row is not None and row.pipeline_id == recipe.id:  # never another recipe's
            row.active = False
            session.add(row)
    known = {
        row.text
        for row in session.exec(
            select(Lesson).where(Lesson.pipeline_id == recipe.id, col(Lesson.active).is_(True))
        ).all()
    }
    for text in result.lessons_to_add:
        text = text.strip()
        if text and text not in known:
            session.add(Lesson(pipeline_id=recipe.id, text=text, source=LessonSource.analytics))
            known.add(text)
    session.flush()
    active = list(
        session.exec(
            select(Lesson)
            .where(Lesson.pipeline_id == recipe.id, col(Lesson.active).is_(True))
            .order_by(col(Lesson.created_at), col(Lesson.id))
        ).all()
    )
    # Over the cap, the analyst's oldest lessons retire first; the
    # owner's own lessons are never trimmed for them.
    excess = len(active) - MAX_ACTIVE_LESSONS
    if excess > 0:
        for row in [r for r in active if r.source == LessonSource.analytics][:excess]:
            row.active = False
            session.add(row)
    session.commit()


async def run_due_analysis(
    session: Session, config: Config, now: datetime | None = None
) -> None:
    """Learn from new mature snapshots, at most once a day per recipe (L2).

    The once-a-day gate is `Pipeline.last_analysis_at`, stamped on
    every attempt, so a failed call waits a day instead of retrying
    every tick. “New since last success” is measured against the
    recipe's newest `analytics` cost event — a successful call writes
    one, so it stays the success record, and a failure never consumes
    the snapshots it missed. One recipe's failure never stops the
    others; a blocked budget just defers (no stamp, no spend).
    """
    now = _utc(now or datetime.now(UTC))
    recipes = session.exec(
        select(Pipeline).where(col(Pipeline.deleted_at).is_(None)).order_by(col(Pipeline.id))
    ).all()
    for recipe in recipes:
        if recipe.last_analysis_at is not None and now - _utc(
            recipe.last_analysis_at
        ) < timedelta(hours=24):
            continue
        last_success = session.exec(
            select(CostEvent)
            .where(CostEvent.stage == Stage.analytics, CostEvent.pipeline_id == recipe.id)
            .order_by(col(CostEvent.created_at).desc(), col(CostEvent.id).desc())
        ).first()
        since = last_success.created_at if last_success else None
        if not _has_new_mature_snapshot(session, recipe, since):
            continue
        try:
            result = await analyst.analyse_pipeline(session, recipe, config)
            _apply_lessons(session, recipe, result)
        except costs.BudgetExceeded:
            # Nothing was spent; try again next tick, when the budget
            # may have room. The attempt is deliberately not stamped.
            log.info("Analysis of %r deferred: monthly budget reached", recipe.name)
            session.rollback()
            continue
        except Exception:  # noqa: BLE001 — one recipe must not stop the rest
            log.exception("Analysis of %r failed; will retry tomorrow", recipe.name)
            session.rollback()
        recipe.last_analysis_at = now
        session.add(recipe)
        session.commit()


async def advance_due_videos(session: Session, config: Config) -> None:
    while True:
        video = session.exec(
            select(Video)
            .where(col(Video.status).in_(_WORKING))
            .order_by(col(Video.created_at), col(Video.id))
        ).first()
        if video is None:
            return
        before = (video.id, VideoStatus(video.status))
        await pipeline.advance(session, video, config)
        session.expire_all()
        after = session.get(Video, before[0])
        if after is None or (after.id, VideoStatus(after.status)) == before:
            return  # no progress; never spin on one video


async def tick(session: Session, config: Config) -> None:
    """One pass of due work, in the worker's order.

    Each step reads its own clock when it starts: draining the video
    queue can take minutes, and a snapshot must be labelled by when
    its counts are actually fetched. The daily clean-up decision
    stays with `run_worker`.
    """
    create_due_videos(session)
    await advance_due_videos(session, config)
    await take_due_snapshots(session, config)
    await run_due_analysis(session, config)


async def run_worker(config: Config, engine: Engine) -> None:
    """The loop itself. One failure is logged; the loop keeps going."""
    last_clean: datetime | None = None
    while True:
        try:
            with Session(engine) as session:
                await tick(session, config)
                # ponytail: in-memory daily timer — a restart just cleans
                # again sooner, and cleaning twice is harmless.
                now = datetime.now(UTC)
                if last_clean is None or now - last_clean >= timedelta(hours=24):
                    retention.clean(session, config, now=now)
                    last_clean = now
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must survive one bad tick
            log.exception("Worker loop step failed; will try again")
        await asyncio.sleep(30)
