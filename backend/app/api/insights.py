"""Insights: the lessons and the per-video numbers (L3).

A video row's numbers come from its latest snapshot (highest
checkpoint); only published videos are listed. All of the recipe's
lessons are listed, switched-off ones too, so they can be switched
back on. Without `pipeline_id`, everything is listed.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import CostEvent, Lesson, Snapshot, Video, VideoStatus

router = APIRouter()


class LessonUpdate(BaseModel):
    active: bool


def _get_or_404(session: Session, lesson_id: int) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "That lesson could not be found. It may have been deleted.")
    return lesson


@router.get("/insights")
def insights(pipeline_id: int | None = None, session: Session = Depends(get_session)) -> dict:
    lesson_query = select(Lesson).order_by(col(Lesson.id))
    video_query = (
        select(Video)
        .where(Video.status == VideoStatus.published)
        .order_by(col(Video.published_at).desc(), col(Video.id).desc())
    )
    if pipeline_id is not None:
        lesson_query = lesson_query.where(Lesson.pipeline_id == pipeline_id)
        video_query = video_query.where(Video.pipeline_id == pipeline_id)
    lessons = session.exec(lesson_query).all()

    rows = []
    for video in session.exec(video_query).all():
        snaps = session.exec(select(Snapshot).where(Snapshot.video_id == video.id)).all()
        latest = max(snaps, key=lambda s: (s.checkpoint_hours, s.id or 0)) if snaps else None
        cost = sum(
            e.cost_usd
            for e in session.exec(select(CostEvent).where(CostEvent.video_id == video.id)).all()
        )
        rows.append(
            {
                "id": video.id,
                "title": video.title,
                "published_at": video.published_at,
                "views": latest.views if latest else 0,
                "likes": latest.likes if latest else 0,
                "comments": latest.comments if latest else 0,
                "avg_view_percent": latest.avg_view_percent if latest else None,
                "cost_usd": cost,
            }
        )
    return {"lessons": [row.model_dump(mode="json") for row in lessons], "videos": rows}


MAX_ACTIVE_LESSONS = 10


@router.put("/lessons/{lesson_id}")
def update_lesson(
    lesson_id: int, body: LessonUpdate, session: Session = Depends(get_session)
) -> Lesson:
    lesson = _get_or_404(session, lesson_id)
    if body.active and not lesson.active:
        active = session.exec(
            select(Lesson).where(
                Lesson.pipeline_id == lesson.pipeline_id, col(Lesson.active).is_(True)
            )
        ).all()
        if len(active) >= MAX_ACTIVE_LESSONS:
            raise HTTPException(
                422,
                "Ten lessons are already on for this recipe. Switch one off "
                "first, then turn this one on.",
            )
    lesson.active = body.active
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, session: Session = Depends(get_session)) -> Response:
    lesson = _get_or_404(session, lesson_id)
    session.delete(lesson)
    session.commit()
    return Response(status_code=204)
