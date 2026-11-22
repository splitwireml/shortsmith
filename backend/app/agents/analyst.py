"""Analyst: recent numbers in, lesson changes out (L2).

Sees a compact table of the recipe's last 20 published videos and
its current active lessons (with ids, so it can retire them).
Applying the changes — and the 10-lesson cap — is the scheduler's
job; this file only makes the one call.
"""

from pydantic import BaseModel
from pydantic_ai import Agent
from sqlmodel import Session, col, select

from app.agents.base import run_agent
from app.config import Config
from app.models import Lesson, Pipeline, Snapshot, Stage, Video, VideoStatus, is_on_youtube, latest_snapshot


class Analysis(BaseModel):
    lessons_to_add: list[str] = []
    lesson_ids_to_retire: list[int] = []


agent: Agent[None, Analysis] = Agent(
    output_type=Analysis,
    instructions=(
        "You study how one kind of YouTube Short has been performing and "
        "turn the numbers into a few short lessons for the planner. Each "
        "lesson is one plain sentence the next video can follow. Add a "
        "lesson only when the numbers really support it, retire a lesson "
        "by its id when the numbers contradict it, and never restate a "
        "lesson that is already listed. Fewer, clearer lessons beat many."
    ),
)


def _rating_word(rating: int) -> str:
    return {1: "thumbs up", -1: "thumbs down"}.get(rating, "—")


def analysis_prompt(
    pipeline: Pipeline, rows: list[tuple[Video, Snapshot | None]], lessons: list[Lesson]
) -> str:
    lines = [
        f"Recipe: {pipeline.name} ({pipeline.niche})",
        "",
        "Recent published videos (title · hook · seconds · views · likes · "
        "average % viewed · the owner's rating):",
    ]
    for video, snap in rows:
        plan = video.plan or {}
        scenes = plan.get("scenes") or []
        seconds = sum(int(s.get("seconds") or 0) for s in scenes) or pipeline.target_seconds
        if snap is None:
            numbers = "numbers not collected yet"
        else:
            percent = f"{snap.avg_view_percent:.0f}%" if snap.avg_view_percent is not None else "—"
            numbers = (
                f"{snap.views} views · {snap.likes} likes · {percent} viewed "
                f"(at {snap.checkpoint_hours}h after publishing)"
            )
        lines.append(
            f"- {video.title} · {plan.get('hook') or '—'} · {seconds}s · "
            f"{numbers} · {_rating_word(video.rating)}"
        )
    lines += ["", "Current lessons (retire by id):"]
    lines += [
        f"- [id {lesson.id}] ({'from the owner' if lesson.source.value == 'you' else 'from the numbers'}) {lesson.text}"
        for lesson in lessons
    ] or ["- (none yet)"]
    return "\n".join(lines)


async def analyse_pipeline(session: Session, pipeline: Pipeline, config: Config) -> Analysis:
    """One analyst call for a recipe; the cost lands under `analytics`."""
    # Practice uploads never really aired; their numbers teach
    # nothing. Filtered here, before the limit, so a run of practice
    # videos cannot push the real ones out of the 20-video window.
    published = session.exec(
        select(Video)
        .where(Video.pipeline_id == pipeline.id, Video.status == VideoStatus.published)
        .order_by(col(Video.published_at).desc(), col(Video.id).desc())
    ).all()
    videos = [video for video in published if is_on_youtube(video)][:20]
    rows: list[tuple[Video, Snapshot | None]] = []
    for video in videos:
        snaps = session.exec(select(Snapshot).where(Snapshot.video_id == video.id)).all()
        rows.append((video, latest_snapshot(snaps)))
    lessons = list(
        session.exec(
            select(Lesson)
            .where(Lesson.pipeline_id == pipeline.id, col(Lesson.active).is_(True))
            .order_by(col(Lesson.created_at), col(Lesson.id))
        ).all()
    )
    return await run_agent(
        agent,
        analysis_prompt(pipeline, rows, lessons),
        stage=Stage.analytics,
        session=session,
        config=config,
        reason=f"Studied how “{pipeline.name}” videos are doing",
        pipeline=pipeline,
    )
