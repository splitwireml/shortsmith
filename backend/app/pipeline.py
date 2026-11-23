"""The video state machine: one function per stage, plus `advance`.

`advance(session, video, config)` runs the stage the video is waiting for,
saves the result, and never raises: a failing stage leaves the video
`failed` with a plain-language reason and `failed_status` set, so Retry
can resume there. Finished clips keep their `storage_key`, so a retry —
or remaking one clip the reviewer named — never pays twice (V3, V4).

Each stage returns the next status; `advance` saves the successful
transition. Paid checkpoints inside a stage (a finished clip and its
cost) are still committed at once by `costs.record`.

Publishing (`approved`) guards against a double upload (Y2): a stored
YouTube id means “already up”, and the `publishing` status is
committed before any byte is sent, so a crash mid-upload can never
silently retry — start-up turns it into a plain failure instead.
"""

import asyncio
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app import costs, db, media, stitch, youtube
from app.agents import planner, reviewer
from app.config import Config
from app.models import ApprovalMode, Clip, Pipeline, Stage, UnitKind, Video, VideoStatus
from app.storage import Storage

# ponytail: flat reserve for one text call (planning, review). The
# real token cost is cents and unknowable before the call, so reserve
# a dime instead of estimating.
TEXT_RESERVE_USD = 0.10


def _clip_key(video_id: int, index: int) -> str:
    return f"videos/{video_id}/clip_{index}.mp4"


def _final_key(video_id: int) -> str:
    return f"videos/{video_id}/final.mp4"


def _thumb_key(video_id: int) -> str:
    return f"videos/{video_id}/thumb.png"


def _clips(session: Session, video: Video) -> list[Clip]:
    return list(
        session.exec(
            select(Clip).where(Clip.video_id == video.id).order_by(col(Clip.index))
        ).all()
    )


async def _plan(session: Session, video: Video, config: Config) -> VideoStatus:
    # Reserve the whole video up front: never spend even the planner's
    # cents on a video whose clips (dollars) would not fit the caps.
    # In practice mode the media is free, so only the text call itself
    # is reserved — a small cap must not block a practice run.
    settings = db.get_settings(session)
    recipe = session.get(Pipeline, video.pipeline_id)
    if settings.practice_mode:
        upcoming = TEXT_RESERVE_USD
    elif recipe is not None:
        upcoming = costs.estimate_video_usd(
            settings, recipe.target_seconds, recipe.video_resolution
        ) + costs.estimate_thumbnail_usd(settings)
    else:
        upcoming = 0.0
    costs.check_budget(session, video, upcoming_usd=upcoming)
    plan = await planner.plan_video(session, video, config)
    for old in _clips(session, video):
        session.delete(old)
    video.title = plan.title
    video.plan = plan.model_dump()
    session.add(video)
    session.add_all(
        [
            Clip(video_id=video.id, index=i, prompt=scene.prompt, seconds=scene.seconds)
            for i, scene in enumerate(plan.scenes)
        ]
    )
    return VideoStatus.generating


async def _generate(session: Session, video: Video, config: Config) -> VideoStatus:
    # Snapshot, not the live row: commits in this pass would refresh it, so
    # a switch flipped mid-pass must wait for the next pass.
    settings = db.get_settings(session).model_copy()
    recipe = session.get(Pipeline, video.pipeline_id)
    if recipe is None:
        raise RuntimeError("This video's recipe could not be found, so its clips cannot be made.")
    resolution = recipe.video_resolution
    storage = Storage(config.media_dir)
    clips = _clips(session, video)
    if not clips:
        raise RuntimeError("This video has no scenes to make yet. Press Retry to plan it again.")
    plan = video.plan or {}
    style = plan.get("style_bible") or ""
    scenes = plan.get("scenes") or []
    thumb_prompt = plan.get("thumbnail_prompt") or video.title or "Video thumbnail"
    thumb_key = _thumb_key(video.id)
    missing = [clip for clip in clips if clip.storage_key is None]
    thumb_missing = not storage.exists(thumb_key)
    upcoming = 0.0
    if not settings.practice_mode:
        upcoming = costs.estimate_video_usd(
            settings, sum(c.seconds for c in missing), resolution
        )
        if thumb_missing:
            upcoming += costs.estimate_thumbnail_usd(settings)
    costs.check_budget(session, video, upcoming_usd=upcoming)
    if settings.practice_mode and (missing or thumb_missing) and not video.practice:
        # This video's media is practice media from here on, whatever the
        # switch says later; saved at once so a later failure keeps it.
        video.practice = True
        session.add(video)
        session.commit()

    # Thumbnail first: every clip call gets it as a subject reference, so
    # the clips look like one video.
    if thumb_missing:
        thumb = await media.generate_thumbnail(thumb_prompt, settings=settings, config=config)
        storage.put(thumb_key, thumb.data)
        costs.record(
            session,
            stage=Stage.thumbnail,
            model=settings.image_model,
            reason="Thumbnail picture",
            units=thumb.units,
            unit_kind=thumb.unit_kind,
            free=settings.practice_mode,
            video=video,
        )
    thumb_bytes = storage.path(thumb_key).read_bytes()

    for clip in missing:
        # The style bible rides along on every clip for a consistent look;
        # the stored prompt stays the scene prompt alone, so a remade clip
        # can simply replace it.
        prompt = f"{style}\n\n{clip.prompt}" if style else clip.prompt
        # The planned narration steers the clip's audio. Looked up by index
        # (not stored on the clip) so a remade clip keeps its line even
        # though the reviewer replaced its visual prompt.
        narration = ""
        if clip.index < len(scenes):
            narration = (scenes[clip.index] or {}).get("narration") or ""
        if narration:
            prompt += f'\n\nNarration: "{narration}"'
        try:
            made = await media.generate_clip(
                prompt,
                clip.seconds,
                resolution=resolution,
                settings=settings,
                config=config,
                reference_image=thumb_bytes,
            )
        except media.PaidButNotDelivered:
            # The clip was charged for but its file never arrived:
            # the ledger still records it (C1), then the stage fails.
            costs.record(
                session,
                stage=Stage.video,
                model=settings.video_model,
                reason=(
                    f"Clip {clip.index + 1} of {len(clips)} — {clip.seconds} s of "
                    "video (paid for, but the file never arrived)"
                ),
                units=float(clip.seconds),
                unit_kind=UnitKind.video_seconds,
                video=video,
                resolution=resolution,
            )
            raise
        key = _clip_key(video.id, clip.index)
        storage.put(key, made.data)
        clip.storage_key = key
        session.add(clip)
        # record() commits at once, saving this clip and its cost together:
        # either both survive a later failure or neither does (V4).
        costs.record(
            session,
            stage=Stage.video,
            model=settings.video_model,
            reason=f"Clip {clip.index + 1} of {len(clips)} — {clip.seconds} s of video",
            units=made.units,
            unit_kind=made.unit_kind,
            free=settings.practice_mode,
            resolution=resolution,
            video=video,
        )

    paths = [storage.path(clip.storage_key) for clip in _clips(session, video)]
    await asyncio.to_thread(stitch.stitch, paths, storage.path(_final_key(video.id)), resolution)
    return VideoStatus.reviewing


async def _review(session: Session, video: Video, config: Config) -> VideoStatus:
    costs.check_budget(session, video, upcoming_usd=TEXT_RESERVE_USD)
    storage = Storage(config.media_dir)
    final_key = _final_key(video.id)
    if not storage.exists(final_key):
        raise RuntimeError("The finished video file is missing, so it cannot be checked.")
    review = await reviewer.review_video(session, video, config, storage.path(final_key))
    video.review = review.model_dump()
    by_index = {clip.index: clip for clip in _clips(session, video)}
    bad = [item for item in review.bad_clips if item.index in by_index]
    if bad and video.review_rounds < 1:
        # Remake only the named clips, with the reviewer's better prompts,
        # at most one round (V3). Clearing the key is the remake signal.
        for item in bad:
            clip = by_index[item.index]
            clip.prompt = item.better_prompt
            clip.storage_key = None
            session.add(clip)
        video.review_rounds += 1
        return VideoStatus.generating
    recipe = session.get(Pipeline, video.pipeline_id)
    auto = (
        recipe is not None
        and recipe.approval_mode == ApprovalMode.auto
        and not video.is_test  # a test video always waits for a person (P4)
        and review.score >= recipe.auto_approve_score
    )
    return VideoStatus.approved if auto else VideoStatus.awaiting_approval


async def _publish(session: Session, video: Video, config: Config) -> VideoStatus:
    if video.youtube_id:  # already uploaded once — never again (Y2)
        video.published_at = video.published_at or datetime.now(UTC)
        return VideoStatus.published
    recipe = session.get(Pipeline, video.pipeline_id)
    if recipe is None:
        raise RuntimeError("This video's recipe could not be found, so it cannot be published.")
    storage = Storage(config.media_dir)
    final_key = _final_key(video.id)
    if not storage.exists(final_key):
        raise RuntimeError("The finished video file is missing, so it cannot be published.")
    thumb_key = _thumb_key(video.id)
    settings = db.get_settings(session)
    plan = video.plan or {}
    # The lock is committed before any byte is sent: a crash mid-upload
    # leaves `publishing` behind, which start-up recovery reports
    # instead of risking a second upload.
    video.status = VideoStatus.publishing
    session.add(video)
    session.commit()
    youtube_id = await asyncio.to_thread(
        youtube.upload,
        config,
        video_path=storage.path(final_key),
        title=video.title or plan.get("title") or "Untitled",
        description=plan.get("description") or "",
        tags=list(plan.get("tags") or []),
        privacy=recipe.visibility.value,
        practice=settings.practice_mode or video.practice,
    )
    # The id is saved the moment YouTube hands it over, before any
    # thumbnail work: a restart during processing can no longer lose
    # a video YouTube already has.
    video.youtube_id = str(youtube_id)
    video.published_at = datetime.now(UTC)
    video.status = VideoStatus.published
    session.add(video)
    session.commit()
    if storage.exists(thumb_key):
        note = await asyncio.to_thread(
            youtube.set_thumbnail, config, video.youtube_id, storage.path(thumb_key)
        )
        if note:  # published fine; the note rides along on the video page
            video.error = note
    return VideoStatus.published


INTERRUPTED_UPLOAD_MESSAGE = (
    "The upload was interrupted. Check your YouTube channel; "
    "if the video is not there, press Retry."
)


def recover_publishing(session: Session) -> None:
    """Start-up: a video left in `publishing` was cut off mid-upload.

    It becomes `failed` from `approved` (`publishing` is a lock, not a
    stage), so Retry re-enters publish — after the user has checked
    the channel, as the message says. # ponytail: we do not query
    YouTube to auto-resolve this.
    """
    stuck = session.exec(select(Video).where(Video.status == VideoStatus.publishing)).all()
    for video in stuck:
        video.status = VideoStatus.failed
        video.failed_status = VideoStatus.approved
        video.error = INTERRUPTED_UPLOAD_MESSAGE
        session.add(video)
    if stuck:
        session.commit()


def _plain_message(exc: Exception) -> str:
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    if not lines:
        return "Something went wrong while making this video. Press Retry to try again."
    return lines[0][:500]


def _fail(session: Session, video: Video, where: VideoStatus, message: str) -> None:
    session.rollback()
    fresh = session.get(Video, video.id)
    if fresh is None:
        return
    fresh.status = VideoStatus.failed
    fresh.failed_status = where
    fresh.error = message
    session.add(fresh)
    session.commit()


async def advance(session: Session, video: Video, config: Config) -> Video:
    """Run the one stage this video is waiting for. Resting states do nothing."""
    stages = {
        VideoStatus.queued: _plan,
        VideoStatus.generating: _generate,
        VideoStatus.reviewing: _review,
        VideoStatus.approved: _publish,
    }
    where = VideoStatus(video.status)
    stage_fn = stages.get(where)
    if stage_fn is None:
        return video
    try:
        # Cleared before, not after: publish may leave a thumbnail note
        # in `error` on an otherwise successful run.
        video.error = None
        video.status = await stage_fn(session, video, config)
        video.failed_status = None
        session.add(video)
        session.commit()
    except asyncio.CancelledError:
        raise
    except costs.BudgetExceeded as exc:
        _fail(session, video, where, str(exc))
    except Exception as exc:  # noqa: BLE001 — the video page must always say why
        _fail(session, video, where, _plain_message(exc))
    return video
