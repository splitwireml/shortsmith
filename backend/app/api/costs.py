"""Money spent: the summary for the costs page and the raw events (C2, C4)."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app import costs
from app.db import get_session
from app.models import CostEvent

router = APIRouter()


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
