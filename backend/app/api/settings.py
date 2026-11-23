"""The one Settings row: budgets, retention, practice mode, models (H3).

Secrets live in Config, never in Settings, so this route can return the
row as it is.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session

from app import costs
from app.db import get_session, get_settings
from app.models import Settings

router = APIRouter()

_MODEL_FIELDS = (
    "planner_model",
    "reviewer_model",
    "analyst_model",
    "helper_model",
    "video_model",
    "image_model",
)


class SettingsUpdate(BaseModel):
    """Any subset of the settings; read-only extras (id, created_at) are ignored."""

    model_config = ConfigDict(extra="ignore")

    monthly_budget_usd: float | None = None
    per_video_cap_usd: float | None = None
    retention_days: int | None = None
    max_storage_gb: float | None = None
    practice_mode: bool | None = None
    onboarding_done: bool | None = None
    planner_model: str | None = None
    planner_effort: str | None = None
    reviewer_model: str | None = None
    reviewer_effort: str | None = None
    analyst_model: str | None = None
    analyst_effort: str | None = None
    helper_model: str | None = None
    helper_effort: str | None = None
    video_model: str | None = None
    image_model: str | None = None


@router.get("/settings")
def read_settings(session: Session = Depends(get_session)) -> Settings:
    return get_settings(session)


@router.put("/settings")
def update_settings(body: SettingsUpdate, session: Session = Depends(get_session)) -> Settings:
    # A null means "leave it alone"; nothing here can be emptied.
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    # Never save a model the ledger cannot price: an unpriced call
    # would otherwise fail after the money was spent. One check for
    # every role; which model suits a role is the caller's choice.
    for field in _MODEL_FIELDS:
        if field in data and data[field] not in costs.PRICES:
            raise HTTPException(
                422,
                f"Shortsmith does not know the model “{data[field]}”. "
                "Check the model name under Advanced settings.",
            )
    settings = get_settings(session)
    for field, value in data.items():
        setattr(settings, field, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings
