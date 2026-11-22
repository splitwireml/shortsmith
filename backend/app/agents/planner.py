"""Planner: recipe brief in, a full video plan out (V2).

Sees only the brief, up to 10 active lessons (the user's own first) and
the last 15 titles of the same recipe. Nothing else.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from sqlalchemy import case
from sqlmodel import Session, col, select

from app.agents.base import run_agent
from app.config import Config
from app.models import Lesson, LessonSource, Pipeline, Stage, Video


class Scene(BaseModel):
    prompt: str
    seconds: int = Field(ge=3, le=15)  # one clip is 3–15 whole seconds
    narration: str = ""


class VideoPlan(BaseModel):
    title: str
    hook: str
    description: str
    tags: list[str]
    style_bible: str
    thumbnail_prompt: str
    scenes: list[Scene] = Field(min_length=1)


agent: Agent[None, VideoPlan] = Agent(
    output_type=VideoPlan,
    instructions=(
        "You plan one YouTube Short. Follow the recipe brief exactly, use the "
        "lessons, and do not repeat a recent title. Give a title, a hook for "
        "the first two seconds, a description, tags, a short style bible "
        "describing the look so every scene matches, a thumbnail prompt, and "
        "the scenes in order. Each scene is one clip with a visual prompt, "
        "its length in seconds, and the narration line if any. The narration "
        "must fit inside its clip: keep it to about two words per second of "
        "the scene (for example, at most six words in a 3-second clip), or "
        "it will be cut off mid-sentence."
    ),
)


def brief_prompt(pipeline: Pipeline, lessons: list[Lesson], titles: list[str]) -> str:
    """Everything the planner is shown, and nothing more (V2)."""
    lines = [
        f"Recipe: {pipeline.name}",
        f"Topic: {pipeline.niche}",
        f"Goal: {pipeline.objective}",
        f"Audience: {pipeline.audience}",
        f"Region and language notes: {pipeline.region_notes or '—'}",
        f"Genre and tone: {pipeline.genre}",
        f"Art style: {pipeline.art_style}",
        f"Target length: about {pipeline.target_seconds} seconds in total",
        f"Extra notes: {pipeline.extra_notes or '—'}",
        "",
        "Lessons (follow these):",
    ]
    lines += [f"- {lesson.text}" for lesson in lessons] or ["- (none yet)"]
    lines += ["", "Recent titles for this recipe (do not repeat these):"]
    lines += [f"- {title}" for title in titles] or ["- (none yet)"]
    lines += [
        "",
        "Each scene is one clip of 3 to 15 whole seconds. Split the video "
        "into enough scenes to reach the target length.",
    ]
    return "\n".join(lines)


async def plan_video(session: Session, video: Video, config: Config) -> VideoPlan:
    pipeline = session.get(Pipeline, video.pipeline_id)
    if pipeline is None:
        raise RuntimeError("This video's recipe could not be found, so it cannot be planned.")
    # The user's own lessons first, newest first inside each group.
    lessons = list(
        session.exec(
            select(Lesson)
            .where(Lesson.pipeline_id == pipeline.id, col(Lesson.active).is_(True))
            .order_by(
                case((Lesson.source == LessonSource.you, 0), else_=1),
                col(Lesson.created_at).desc(),
                col(Lesson.id).desc(),
            )
            .limit(10)
        ).all()
    )
    titles = list(
        session.exec(
            select(Video.title)
            .where(Video.pipeline_id == pipeline.id, Video.id != video.id, Video.title != "")
            .order_by(col(Video.created_at).desc(), col(Video.id).desc())
            .limit(15)
        ).all()
    )
    return await run_agent(
        agent,
        brief_prompt(pipeline, lessons, titles),
        stage=Stage.planning,
        session=session,
        config=config,
        reason="Planned the video",
        video=video,
    )
