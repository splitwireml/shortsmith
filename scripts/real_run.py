"""One real end-to-end run: a single paid 20 s Short, published private.

    cd backend && uv run python ../scripts/real_run.py

This spends real money and uploads for real. It goes through the
app's own pipeline (planner, media, stitching, review, publish), so
every paid call is written to the cost ledger. Guards, all checked
before anything is spent: the app itself must not be running and no
other video may be in flight (the run flips the shared practice
switch, so a second worker would go live with it), YouTube must be
connected with a live sign-in, the all-time ledger plus this run's
video estimate must stay within $10, and no video may already have
reached a real upload. Practice mode is switched off for the run
and back on again on every exit path. Nothing is retried: a failed
stage ends the run with a non-zero exit code.

Importing this module does nothing (it never reads `.env`); the run
starts only in `main()`. `main(config)` takes a Config so the tests
can drive it against a temporary folder with fakes.
"""

import asyncio
import socket
import sys
from pathlib import Path

# Run as `../scripts/real_run.py` from backend/, Python's path starts
# in scripts/; the app package lives in backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import func  # noqa: E402
from sqlmodel import Session, col, select  # noqa: E402

from app import costs, db, pipeline, youtube  # noqa: E402
from app.config import Config  # noqa: E402
from app.models import (  # noqa: E402
    ApprovalMode,
    CostEvent,
    Pipeline,
    Video,
    VideoStatus,
    Visibility,
)

LEDGER_LIMIT_USD = 10.0
TARGET_SECONDS = 20  # two scenes of 10 s (see the recipe's extra notes)
RECIPE_NAME = "Real-run test (one private Short)"
_WORKING = (VideoStatus.queued, VideoStatus.generating, VideoStatus.reviewing)
# Another video in one of these states is in flight; the run must not
# flip the shared practice switch underneath it.
_IN_FLIGHT = (*_WORKING, VideoStatus.approved, VideoStatus.publishing)


def _refuse(message: str) -> int:
    print(f"Real run refused: {message}", file=sys.stderr)
    return 1


def _app_is_running() -> bool:
    """Whether something (presumably the app) answers on its port."""
    try:
        with socket.create_connection(("127.0.0.1", 8484), timeout=0.5):
            return True
    except OSError:
        return False


def _reached_upload(video: Video) -> bool:
    """Whether this video ever got to a real upload attempt.

    A saved YouTube id is proof; so are the publishing lock and a
    failure out of publish, where YouTube may have the video even
    though no id was ever saved here.
    """
    if video.youtube_id and not video.youtube_id.startswith("practice-"):
        return True
    if VideoStatus(video.status) == VideoStatus.publishing:
        return True
    return (
        VideoStatus(video.status) == VideoStatus.failed
        and video.failed_status is not None
        and VideoStatus(video.failed_status) == VideoStatus.approved
    )


def _create_recipe(session: Session) -> Pipeline:
    """A fresh paused, private, manual recipe, made for this run only.

    Fresh every time (never looked up by name), so an edited older
    recipe can never change this run's visibility or length.
    """
    recipe = Pipeline(
        name=RECIPE_NAME,
        niche="Cute and surprising animal moments",
        objective="Delight viewers with one charming animal moment",
        audience="Animal lovers of all ages",
        region_notes="Plain international English",
        genre="Feel-good animal stories",
        art_style="Soft, friendly cartoon animals in bright colours",
        target_seconds=TARGET_SECONDS,
        every_days=7,
        videos_per_run=1,
        approval_mode=ApprovalMode.manual,
        visibility=Visibility.private,
        extra_notes=(
            "Make exactly two scenes of 10 seconds each. "
            "One animal hero, a tiny problem, and a happy ending."
        ),
        active=False,  # paused: the scheduler never queues from it
    )
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    return recipe


def _fresh(session: Session, video_id: int) -> Video:
    session.expire_all()
    video = session.get(Video, video_id)
    assert video is not None  # we just created it in this run
    return video


async def _run(config: Config) -> int:
    engine = db.make_engine(config)
    db.init_db(engine)
    try:
        with Session(engine) as session:
            try:
                # Every refusal below is decided before a cent is spent:
                # nothing is queued, planned or generated on these paths.
                if _app_is_running():
                    return _refuse(
                        "the Shortsmith app appears to be running. Stop it "
                        "first (close its window), then run this again — the "
                        "test run must have the app's data to itself."
                    )
                if not config.youtube_token_path.is_file():
                    return _refuse(
                        "YouTube is not connected yet (no sign-in was found). "
                        "Connect YouTube in the app, then run this again."
                    )
                connection = youtube.status(config)
                if not connection["connected"] or connection["needs_reconnect"]:
                    return _refuse(
                        "the YouTube sign-in is not usable (it may have "
                        "expired). Reconnect YouTube in the app, then run "
                        "this again."
                    )
                settings = db.get_settings(session)
                ledger_total = float(
                    session.exec(
                        select(func.coalesce(func.sum(CostEvent.cost_usd), 0.0))
                    ).one()
                )
                estimate = costs.estimate_video_usd(
                    settings, TARGET_SECONDS
                ) + costs.estimate_thumbnail_usd(settings)
                if ledger_total + estimate > LEDGER_LIMIT_USD:
                    return _refuse(
                        f"the cost ledger already holds ${ledger_total:.2f} and "
                        f"this run needs about ${estimate:.2f} more, which would "
                        f"pass the ${LEDGER_LIMIT_USD:.2f} limit for the test run."
                    )
                in_flight = session.exec(
                    select(Video).where(col(Video.status).in_(_IN_FLIGHT))
                ).first()
                if in_flight is not None:
                    return _refuse(
                        f"another video (id {in_flight.id}) is already being "
                        "made or published. Let it finish or fail first, "
                        "then run this again."
                    )
                attempted = [
                    video
                    for video in session.exec(select(Video)).all()
                    if _reached_upload(video)
                ]
                if attempted:
                    return _refuse(
                        "a video has already reached a real upload "
                        f"(video id {attempted[0].id}), so this one-off "
                        "test run will not upload a second one."
                    )

                recipe = _create_recipe(session)

                # Real media and a real upload from here on. The finally
                # below turns practice mode back on however we leave.
                settings.practice_mode = False
                session.add(settings)
                session.commit()

                video = Video(
                    pipeline_id=recipe.id, status=VideoStatus.queued, is_test=True
                )
                session.add(video)
                session.commit()
                session.refresh(video)
                video_id = video.id
                print(f"Making one real test video (id {video_id})…")

                # Plan, generate, review — one pass, no retries. The
                # progress check mirrors the worker loop: a stage that
                # changes nothing must not spin here either.
                while VideoStatus(video.status) in _WORKING:
                    before = VideoStatus(video.status)
                    await pipeline.advance(session, video, config)
                    video = _fresh(session, video_id)
                    if VideoStatus(video.status) == before:
                        break
                if VideoStatus(video.status) != VideoStatus.awaiting_approval:
                    reason = video.error or f"the video stopped at “{video.status}”"
                    print(f"The test video did not finish: {reason}", file=sys.stderr)
                    return 1

                print("The video passed its check. Approving and publishing it privately…")
                video.status = VideoStatus.approved
                session.add(video)
                session.commit()
                await pipeline.advance(session, video, config)  # publish, once
                video = _fresh(session, video_id)
                if VideoStatus(video.status) != VideoStatus.published or not video.youtube_id:
                    reason = video.error or f"the video stopped at “{video.status}”"
                    print(f"The video was not published: {reason}", file=sys.stderr)
                    return 1

                print(f"Published privately as YouTube video {video.youtube_id}.")
                try:
                    numbers = await asyncio.to_thread(
                        youtube.fetch_stats, config, video.youtube_id, with_analytics=True
                    )
                except Exception as exc:  # noqa: BLE001 — say it plainly, do not traceback
                    print(
                        f"The video is published, but reading its numbers failed: {exc}",
                        file=sys.stderr,
                    )
                    return 1
                print("Its numbers right now (with analytics):")
                for name, value in numbers.items():
                    print(f"  {name}: {value}")
                return 0
            finally:
                # Practice mode back on, on every way out of the run.
                session.rollback()
                settings = db.get_settings(session)
                settings.practice_mode = True
                session.add(settings)
                session.commit()
    finally:
        engine.dispose()


def main(config: Config | None = None) -> int:
    """Run the one real test. `None` means the real Config (reads `.env`)."""
    return asyncio.run(_run(config or Config()))


if __name__ == "__main__":
    sys.exit(main())
