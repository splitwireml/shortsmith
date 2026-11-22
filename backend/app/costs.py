"""Money: the price table, recording a paid call, budget checks, summaries.

Prices are copied from docs/research.md (verified 2026-11-22) and live
nowhere else. Days and months are UTC, matching how CostEvent.created_at
is stored.
"""

import calendar
from datetime import UTC, date, datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app import db
from app.models import CostEvent, Pipeline, Settings, Snapshot, Stage, UnitKind, Video, VideoStatus

# Dollars per 1M tokens (research sections 1 and 3). Argon uses the
# post-2026-12-01 rate from day one, so the ledger never understates.
PRICES: dict[str, dict[str, float]] = {
    "gemini-4-hydrogen": {"input_per_1m": 1.50, "output_per_1m": 7.50},
    "gemini-4-argon": {"input_per_1m": 4.00, "output_per_1m": 20.00},
    "gemini-omni-1.2-flash": {
        "input_per_1m": 1.50,
        "output_per_1m": 9.00,  # text out
        "video_output_per_1m": 12.00,  # video out; ~$0.07/s at 720p
    },
    # Per finished image at the smallest standard size (research section 2).
    "gemini-nano-banana-2.1": {"per_image": 0.0336},
    "gemini-3.1-flash-image": {"per_image": 0.067},
    "gemini-3.1-flash-lite-image": {"per_image": 0.0336},
    "gemini-3-pro-image": {"per_image": 0.134},
}

# Video output tokens for one second, by resolution (research section 1).
VIDEO_TOKENS_PER_SECOND = {"360p": 1931, "720p": 5792, "1080p": 8688, "4k": 17376}


class BudgetExceeded(Exception):
    """The next paid step would break a budget; the message is for the user."""


def _as_utc(moment: datetime) -> datetime:
    # SQLite hands some datetimes back without a timezone; they are UTC.
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _price(
    model: str,
    *,
    settings: Settings,
    input_tokens: int,
    output_tokens: int,
    units: float,
    unit_kind: UnitKind,
) -> float:
    rates = PRICES.get(model)
    if rates is None:
        raise ValueError(f"No price is listed for the model {model!r}. Add it to app/costs.py.")
    cost = input_tokens * rates.get("input_per_1m", 0.0) / 1_000_000
    cost += output_tokens * rates.get("output_per_1m", 0.0) / 1_000_000
    if unit_kind == UnitKind.video_seconds:
        tokens_per_second = VIDEO_TOKENS_PER_SECOND.get(settings.video_resolution.lower())
        if tokens_per_second is None or "video_output_per_1m" not in rates:
            raise ValueError(
                f"Video cannot be priced for model {model!r} at "
                f"resolution {settings.video_resolution!r}."
            )
        cost += units * tokens_per_second * rates["video_output_per_1m"] / 1_000_000
    elif unit_kind == UnitKind.images:
        if "per_image" not in rates:
            raise ValueError(f"No per-image price is listed for the model {model!r}.")
        cost += units * rates["per_image"]
    return cost


def record(
    session: Session,
    *,
    stage: Stage | str,
    model: str,
    reason: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    units: float = 0,
    unit_kind: UnitKind | str = UnitKind.tokens,
    video: Video | None = None,
    pipeline: Pipeline | None = None,
) -> CostEvent:
    """Write one cost event and commit at once (C1).

    Committing here is the point: if the stage that called us fails later
    and rolls back, money that was really spent stays in the ledger.
    Saving progress alongside is what lets a later Retry keep finished
    clips instead of paying for them again (V4).
    """
    # Convert once, up front: a mistyped stage or unit kind fails here
    # instead of skipping a charge or writing a row nothing can read.
    stage = stage if isinstance(stage, Stage) else Stage(stage)
    kind = unit_kind if isinstance(unit_kind, UnitKind) else UnitKind(unit_kind)
    event = CostEvent(
        stage=stage,
        model=model,
        reason=reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        units=units,
        unit_kind=kind,
        cost_usd=_price(
            model,
            settings=db.get_settings(session),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            units=units,
            unit_kind=kind,
        ),
        video_id=video.id if video is not None else None,
        pipeline_id=(
            pipeline.id if pipeline is not None else video.pipeline_id if video is not None else None
        ),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _sum_where(session: Session, *where) -> float:
    total = session.exec(
        select(func.coalesce(func.sum(CostEvent.cost_usd), 0.0)).where(*where)
    ).one()
    return float(total)


def _spent_this_month(session: Session) -> float:
    """The one definition of monthly spend: the current UTC month."""
    today = datetime.now(UTC).date()
    start = datetime(today.year, today.month, 1, tzinfo=UTC)
    next_start = (
        datetime(today.year + 1, 1, 1, tzinfo=UTC)
        if today.month == 12
        else datetime(today.year, today.month + 1, 1, tzinfo=UTC)
    )
    return _sum_where(session, CostEvent.created_at >= start, CostEvent.created_at < next_start)


def check_budget(session: Session, video: Video | None, upcoming_usd: float = 0) -> None:
    """Refuse before spending if a cap would be exceeded (C3).

    Raises BudgetExceeded with a plain sentence; reaching a cap exactly
    is allowed. Budgets are read from the Settings row on every call.
    """
    settings = db.get_settings(session)
    if video is not None:
        spent_on_video = _sum_where(session, CostEvent.video_id == video.id)
        if spent_on_video + upcoming_usd > settings.per_video_cap_usd:
            raise BudgetExceeded(
                f"This video has already cost ${spent_on_video:.2f}. Spending about "
                f"${upcoming_usd:.2f} more would go over the "
                f"${settings.per_video_cap_usd:.2f} limit for one video, so nothing was spent."
            )
    spent_this_month = _spent_this_month(session)
    if spent_this_month + upcoming_usd > settings.monthly_budget_usd:
        raise BudgetExceeded(
            f"You have spent ${spent_this_month:.2f} this month. Spending about "
            f"${upcoming_usd:.2f} more would go over your "
            f"${settings.monthly_budget_usd:.2f} monthly budget, so nothing was spent."
        )


def summary(session: Session, start: date, end: date) -> dict:
    """Totals for the costs page (C2); start and end are inclusive UTC dates.

    The month figures always describe the current month, whatever range
    was asked for: the page shows both side by side.
    """
    events = session.exec(select(CostEvent)).all()
    in_range = [e for e in events if start <= _as_utc(e.created_at).date() <= end]

    by_stage = {stage.value: 0.0 for stage in Stage}
    by_pipeline: dict[int | None, float] = {}
    by_day: dict[str, float] = {}
    by_video: dict[int, float] = {}
    for e in in_range:
        by_stage[e.stage.value] = by_stage.get(e.stage.value, 0.0) + e.cost_usd
        by_pipeline[e.pipeline_id] = by_pipeline.get(e.pipeline_id, 0.0) + e.cost_usd
        day = _as_utc(e.created_at).date().isoformat()
        by_day[day] = by_day.get(day, 0.0) + e.cost_usd
        if e.video_id is not None:
            by_video[e.video_id] = by_video.get(e.video_id, 0.0) + e.cost_usd

    pipelines = {p.id: p.name for p in session.exec(select(Pipeline)).all()}
    videos = {v.id: v for v in session.exec(select(Video)).all()}

    snapshots: dict[int, list[Snapshot]] = {}
    for snap in session.exec(select(Snapshot)).all():
        snapshots.setdefault(snap.video_id, []).append(snap)
    # Spend counts for every published video, views only where a snapshot
    # exists yet; the ratio stays empty until some views are known.
    published_spend = 0.0
    latest_views = 0
    for video_id, usd in by_video.items():
        video = videos.get(video_id)
        if video is None or video.status != VideoStatus.published:
            continue
        published_spend += usd
        snaps = snapshots.get(video_id, [])
        if snaps:
            # Latest snapshot wins; its views are a running total, not an increment.
            latest = max(snaps, key=lambda s: (_as_utc(s.created_at), s.checkpoint_hours, s.id or 0))
            latest_views += latest.views
    cost_per_view = published_spend / latest_views if latest_views else None

    today = datetime.now(UTC).date()
    spent = _spent_this_month(session)
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    return {
        "total_usd": sum(e.cost_usd for e in in_range),
        "by_stage": by_stage,
        "by_pipeline": [
            {"pipeline_id": pid, "name": pipelines.get(pid) if pid is not None else None, "usd": usd}
            for pid, usd in sorted(by_pipeline.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
        ],
        "by_day": [{"day": day, "usd": by_day[day]} for day in sorted(by_day)],
        "by_video": [
            {
                "video_id": vid,
                "title": videos[vid].title if vid in videos else None,
                "usd": by_video[vid],
            }
            for vid in sorted(by_video)
        ],
        "cost_per_view": cost_per_view,
        "month": {
            "spent_usd": spent,
            "budget_usd": db.get_settings(session).monthly_budget_usd,
            "projected_usd": spent / today.day * days_in_month,
        },
    }
