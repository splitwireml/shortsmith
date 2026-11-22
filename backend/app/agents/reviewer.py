"""Reviewer: watches the stitched video once, scores it, names bad clips (V3).

Small videos travel inline; larger ones go through the Files API. Clip
indexes in the answer are 0-based, matching `Clip.index` and `clip_0.mp4`.
"""

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, UploadedFile
from pydantic_ai.providers.google import GoogleProvider
from sqlmodel import Session, col, select

from app import media
from app.agents.base import run_agent
from app.config import Config
from app.models import Clip, Stage, Video

# Inline below this; the request limit is 20 MB, so leave headroom.
INLINE_LIMIT_BYTES = 15_000_000


class BadClip(BaseModel):
    index: int = Field(ge=0)
    problem: str
    better_prompt: str


class Review(BaseModel):
    score: int = Field(ge=1, le=10)
    summary: str
    bad_clips: list[BadClip] = []


agent: Agent[None, Review] = Agent(
    output_type=Review,
    instructions=(
        "You review one finished YouTube Short. Watch the whole video, score "
        "it from 1 to 10 for clarity, flow and how well it matches the plan, "
        "and summarise briefly. Name any clip that is broken or clearly off "
        "brief by its index, say what is wrong, and write a better prompt "
        "for remaking just that clip. Name no clip that is merely average."
    ),
)


def _mmss(seconds: int) -> str:
    return f"{seconds // 60:02}:{seconds % 60:02}"


def review_prompt(video: Video, clips: list[Clip]) -> str:
    plan = video.plan or {}
    scenes = plan.get("scenes") or []
    lines = [
        f"Planned title: {plan.get('title') or video.title}",
        f"Planned hook: {plan.get('hook') or '—'}",
        "Scenes in order (index, time in the video, what should happen):",
    ]
    at = 0
    for clip in clips:
        scene = scenes[clip.index] if clip.index < len(scenes) else {}
        text = scene.get("prompt") or clip.prompt
        lines.append(f"- Clip {clip.index}, {_mmss(at)}–{_mmss(at + clip.seconds)}: {text}")
        at += clip.seconds
    lines.append("Use the clip index above when naming a bad clip.")
    return "\n".join(lines)


async def _upload(config: Config, path: Path) -> UploadedFile:
    provider = GoogleProvider(api_key=config.gemini_api_key.get_secret_value())
    client = provider.client
    uploaded = await client.aio.files.upload(file=str(path))
    # A file must finish processing before the model can watch it.
    ready = await media.wait_for_file(
        client.aio.files,
        uploaded.name,
        failed="Google could not process the video for review. Press Retry to try again.",
        slow="The video took too long to prepare for review. Press Retry to try again.",
    )
    return UploadedFile(file_id=ready.uri, media_type=ready.mime_type or "video/mp4", provider_name="google")


async def review_video(session: Session, video: Video, config: Config, final_path: Path) -> Review:
    clips = list(
        session.exec(
            select(Clip).where(Clip.video_id == video.id).order_by(col(Clip.index))
        ).all()
    )
    text = review_prompt(video, clips)
    if final_path.stat().st_size < INLINE_LIMIT_BYTES:
        content: list = [
            BinaryContent(data=final_path.read_bytes(), media_type="video/mp4"),
            text,
        ]
    else:
        content = [await _upload(config, final_path), text]
    return await run_agent(
        agent,
        content,
        stage=Stage.review,
        session=session,
        config=config,
        reason="Watched and scored the video",
        video=video,
    )
