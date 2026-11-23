"""Money spent: the summary for the costs page and the raw events (C2, C4).

`/costs/estimate` prices the recipe form's live estimate (P1) with
the same helpers the pre-spend budget check uses, so the frontend
needs no price table of its own.
"""

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, select

from app import costs
from app.db import get_session, get_settings
from app.models import CostEvent

router = APIRouter()


@router.get("/costs/estimate")
def cost_estimate(
    seconds: float = Query(default=30, gt=0),
    every_days: int = Query(default=1, ge=1),
    videos_per_run: int = Query(default=1, ge=1),
    resolution: Literal["360p", "720p", "1080p", "4k"] = "1080p",
    session: Session = Depends(get_session),
) -> dict:
    settings = get_settings(session)
    per_video = costs.estimate_video_usd(
        settings, seconds, resolution
    ) + costs.estimate_thumbnail_usd(settings)
    # ponytail: a 30-day month — this is a planning estimate, not a bill.
    per_month = per_video * videos_per_run * (30 / every_days)
    return {"per_video_usd": per_video, "per_month_usd": per_month}


@router.get("/costs/summary")
def cost_summary(
    start: date | None = None,
    end: date | None = None,
    session: Session = Depends(get_session),
) -> dict:
    today = datetime.now(UTC).date()
    return costs.summary(session, start or today.replace(day=1), end or today)


@router.get("/costs/events")
def cost_events(
    video_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[CostEvent]:
    query = select(CostEvent).order_by(col(CostEvent.id))
    if video_id is not None:
        query = query.where(CostEvent.video_id == video_id)
    return list(session.exec(query).all())
