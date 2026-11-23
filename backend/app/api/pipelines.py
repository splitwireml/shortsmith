"""Recipes: CRUD, the preset list, and "make a video now" (P1, P2, P4).

Deleting a recipe only marks it deleted: its videos and cost history
keep pointing at a row with a name, but the recipe routes below hide it.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, col, select

from app import costs
from app.agents import helper
from app.db import get_session
from app.models import Pipeline, PipelineBase, Video, VideoStatus
from app.presets import PRESETS

router = APIRouter()


class PipelineUpdate(PipelineBase):
    """A full edit: the UI sends back the whole recipe it loaded, so an
    edit shares PipelineBase's rules. Read-only fields such as id and
    created_at are simply ignored."""

    model_config = ConfigDict(extra="ignore")

    active: bool | None = None


class RunIn(BaseModel):
    count: int = Field(default=1, ge=1, le=3)
    is_test: bool = False


class SuggestIn(BaseModel):
    description: str = Field(min_length=1)


def _get_or_404(session: Session, pipeline_id: int) -> Pipeline:
    pipeline = session.get(Pipeline, pipeline_id)
    if pipeline is None or pipeline.deleted_at is not None:
        raise HTTPException(404, "That recipe could not be found. It may have been deleted.")
    return pipeline


@router.get("/presets")
def list_presets() -> list[dict]:
    return [PipelineBase.model_validate(p).model_dump() for p in PRESETS]


@router.get("/pipelines")
def list_pipelines(session: Session = Depends(get_session)) -> list[Pipeline]:
    query = select(Pipeline).where(col(Pipeline.deleted_at).is_(None)).order_by(col(Pipeline.id))
    return list(session.exec(query).all())


@router.post("/pipelines", status_code=201)
def create_pipeline(body: PipelineBase, session: Session = Depends(get_session)) -> Pipeline:
    pipeline = Pipeline.model_validate(body)
    # A new recipe starts paused: saving one must never start spending.
    # “Make a video now” still works while paused; only the schedule waits.
    pipeline.active = False
    session.add(pipeline)
    session.commit()
    session.refresh(pipeline)
    return pipeline


@router.post("/pipelines/suggest")
async def suggest_pipeline(
    body: SuggestIn, request: Request, session: Session = Depends(get_session)
) -> PipelineBase:
    """Fill the form from one sentence (P3). Nothing is saved."""
    try:
        return await helper.suggest(session, request.app.state.config, body.description)
    except costs.BudgetExceeded as exc:
        raise HTTPException(402, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            502,
            "The assistant could not fill in the recipe just now. "
            "You can fill the form in yourself, or try again in a moment.",
        ) from None


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: int, session: Session = Depends(get_session)) -> Pipeline:
    return _get_or_404(session, pipeline_id)


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(
    pipeline_id: int, body: PipelineUpdate, session: Session = Depends(get_session)
) -> Pipeline:
    pipeline = _get_or_404(session, pipeline_id)
    data = body.model_dump()
    active = data.pop("active")
    for field, value in data.items():
        setattr(pipeline, field, value)
    if active is not None:
        pipeline.active = active
    session.add(pipeline)
    session.commit()
    session.refresh(pipeline)
    return pipeline


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: int, session: Session = Depends(get_session)) -> Response:
    pipeline = _get_or_404(session, pipeline_id)
    pipeline.deleted_at = datetime.now(UTC)
    session.add(pipeline)
    session.commit()
    return Response(status_code=204)


@router.post("/pipelines/{pipeline_id}/run", status_code=201)
def run_pipeline(
    pipeline_id: int, body: RunIn, session: Session = Depends(get_session)
) -> list[Video]:
    """Queue videos now; the worker loop (S3) picks them up from `queued`."""
    _get_or_404(session, pipeline_id)
    videos = [
        Video(pipeline_id=pipeline_id, status=VideoStatus.queued, is_test=body.is_test)
        for _ in range(body.count)
    ]
    session.add_all(videos)
    session.commit()
    for video in videos:
        session.refresh(video)
    return videos
