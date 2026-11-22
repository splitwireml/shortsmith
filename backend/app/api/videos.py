"""Videos: the list and inbox, one video page, and the human decisions (A1–A4).

Approve and reject only work while a video waits for its person. A
rejection reason or a feedback note becomes a lesson at once, word for
word, so the next plan hears it.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Clip, CostEvent, Lesson, LessonSource, Snapshot, Video, VideoStatus
from app.storage import Storage

router = APIRouter()


class RejectIn(BaseModel):
    reason: str | None = None


class FeedbackIn(BaseModel):
    rating: Literal[-1, 0, 1]
    note: str | None = None


def _get_or_404(session: Session, video_id: int) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "That video could not be found. It may have been deleted.")
    return video


def _require_waiting(video: Video) -> None:
    if video.status != VideoStatus.awaiting_approval:
        raise HTTPException(409, "This video is not waiting for your decision right now.")


def _remember(session: Session, video: Video, words: str | None) -> None:
    # Notes become lessons word for word; an empty note teaches nothing.
    if words and words.strip():
        session.add(
            Lesson(pipeline_id=video.pipeline_id, video_id=video.id, text=words, source=LessonSource.you)
        )


@router.get("/videos")
def list_videos(
    pipeline_id: int | None = None,
    status: VideoStatus | None = None,
    session: Session = Depends(get_session),
) -> list[Video]:
    query = select(Video).order_by(col(Video.id))
    if pipeline_id is not None:
        query = query.where(Video.pipeline_id == pipeline_id)
    if status is not None:
        query = query.where(Video.status == status)
    return list(session.exec(query).all())


@router.get("/videos/{video_id}")
def get_video(video_id: int, session: Session = Depends(get_session)) -> dict:
    video = _get_or_404(session, video_id)
    clips = session.exec(
        select(Clip).where(Clip.video_id == video.id).order_by(col(Clip.index))
    ).all()
    events = session.exec(
        select(CostEvent).where(CostEvent.video_id == video.id).order_by(col(CostEvent.id))
    ).all()
    snapshots = session.exec(
        select(Snapshot).where(Snapshot.video_id == video.id).order_by(col(Snapshot.id))
    ).all()
    return {
        **video.model_dump(mode="json"),
        "clips": [clip.model_dump(mode="json") for clip in clips],
        "cost_events": [event.model_dump(mode="json") for event in events],
        "snapshots": [snap.model_dump(mode="json") for snap in snapshots],
    }


@router.post("/videos/{video_id}/approve")
def approve_video(video_id: int, session: Session = Depends(get_session)) -> Video:
    video = _get_or_404(session, video_id)
    _require_waiting(video)
    video.status = VideoStatus.approved
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


@router.post("/videos/{video_id}/reject")
def reject_video(
    video_id: int, body: RejectIn | None = None, session: Session = Depends(get_session)
) -> Video:
    video = _get_or_404(session, video_id)
    _require_waiting(video)
    video.status = VideoStatus.rejected
    session.add(video)
    _remember(session, video, body.reason if body else None)
    session.commit()
    session.refresh(video)
    return video


@router.post("/videos/{video_id}/retry")
def retry_video(video_id: int, session: Session = Depends(get_session)) -> Video:
    video = _get_or_404(session, video_id)
    if video.status != VideoStatus.failed or video.failed_status is None:
        raise HTTPException(409, "Only a video that failed can be retried.")
    # Back to where it failed; work already paid for is kept (V4).
    video.status = video.failed_status
    video.failed_status = None
    video.error = None
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


@router.post("/videos/{video_id}/feedback")
def feedback(video_id: int, body: FeedbackIn, session: Session = Depends(get_session)) -> Video:
    video = _get_or_404(session, video_id)
    video.rating = body.rating
    session.add(video)
    _remember(session, video, body.note)
    session.commit()
    session.refresh(video)
    return video


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Remove the video, its clips and its media. Cost history stays: the
    money was spent whether or not the video is kept."""
    video = _get_or_404(session, video_id)
    storage = Storage(request.app.state.config.media_dir)
    for key in storage.list(f"videos/{video.id}/"):
        storage.delete(key)
    for clip in session.exec(select(Clip).where(Clip.video_id == video.id)).all():
        session.delete(clip)
    for snap in session.exec(select(Snapshot).where(Snapshot.video_id == video.id)).all():
        session.delete(snap)
    session.delete(video)
    session.commit()
    return Response(status_code=204)
