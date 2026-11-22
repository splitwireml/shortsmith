"""Every table and enum in the app (docs/02-architecture.md, "Data model").

Later sprints build on these; S1 only exercises Settings, Pipeline, Video,
CostEvent and Snapshot.
"""

from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class VideoStatus(str, Enum):
    queued = "queued"
    generating = "generating"
    reviewing = "reviewing"
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    publishing = "publishing"
    published = "published"
    rejected = "rejected"
    failed = "failed"
    archived = "archived"


class Stage(str, Enum):
    planning = "planning"
    video = "video"
    thumbnail = "thumbnail"
    review = "review"
    analytics = "analytics"
    help = "help"


class UnitKind(str, Enum):
    tokens = "tokens"
    video_seconds = "video_seconds"
    images = "images"


class ApprovalMode(str, Enum):
    manual = "manual"
    auto = "auto"


class Visibility(str, Enum):
    private = "private"
    unlisted = "unlisted"
    public = "public"


class LessonSource(str, Enum):
    analytics = "analytics"
    you = "you"


class Settings(SQLModel, table=True):
    """Exactly one row; `db.get_settings` creates it with these defaults."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    monthly_budget_usd: float = 30.0
    per_video_cap_usd: float = 6.0
    retention_days: int = 14
    max_storage_gb: float = 5.0
    practice_mode: bool = True
    onboarding_done: bool = False
    planner_model: str = "gemini-4-hydrogen"
    planner_effort: str = "high"
    reviewer_model: str = "gemini-4-argon"
    reviewer_effort: str = "high"
    analyst_model: str = "gemini-4-hydrogen"
    analyst_effort: str = "medium"
    helper_model: str = "gemini-4-hydrogen"
    helper_effort: str = "low"
    video_model: str = "gemini-omni-1.2-flash"
    video_resolution: str = "720p"
    image_model: str = "gemini-nano-banana-2.1"


class PipelineBase(SQLModel):
    """The fields a user fills in; also the POST /pipelines body."""

    name: str
    niche: str
    objective: str
    audience: str
    region_notes: str = ""
    genre: str
    art_style: str
    target_seconds: int = Field(ge=15, le=60)  # P1: a Short here is 15-60 s
    every_days: int = Field(ge=1)
    videos_per_run: int = Field(ge=1)
    approval_mode: ApprovalMode
    auto_approve_score: int = Field(default=8, ge=1, le=10)  # review scores run 1-10
    visibility: Visibility
    extra_notes: str = ""


class Pipeline(PipelineBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    active: bool = True
    last_run_at: datetime | None = None
    # Last analyst attempt (success or failure), for the once-a-day gate;
    # the analytics cost events remain the record of successful runs.
    last_analysis_at: datetime | None = None
    # Set on delete: the row stays for video history and cost reports,
    # but recipe routes hide it and no new work is queued for it.
    deleted_at: datetime | None = None


class Video(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    pipeline_id: int = Field(foreign_key="pipeline.id")
    status: VideoStatus = VideoStatus.queued
    is_test: bool = False
    title: str = ""
    plan: dict | None = Field(default=None, sa_column=Column(JSON))
    review: dict | None = Field(default=None, sa_column=Column(JSON))
    review_rounds: int = 0
    error: str | None = None
    failed_status: VideoStatus | None = None
    youtube_id: str | None = None
    published_at: datetime | None = None
    rating: int = 0  # -1 thumbs down, 0 none, 1 thumbs up
    media_deleted_at: datetime | None = None


class Clip(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    video_id: int = Field(foreign_key="video.id")
    index: int
    prompt: str = ""
    seconds: int = 0
    storage_key: str | None = None  # null until generated; null again = regenerate


class Lesson(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    pipeline_id: int = Field(foreign_key="pipeline.id")
    video_id: int | None = Field(default=None, foreign_key="video.id")
    text: str
    source: LessonSource
    active: bool = True


class CostEvent(SQLModel, table=True):
    """One row per paid AI call; the single source of truth for money (C1)."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    pipeline_id: int | None = Field(default=None, foreign_key="pipeline.id")
    video_id: int | None = Field(default=None, foreign_key="video.id")
    stage: Stage
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    units: float = 0
    unit_kind: UnitKind = UnitKind.tokens
    cost_usd: float = 0
    reason: str = ""


def is_on_youtube(video: "Video") -> bool:
    """Whether the video really aired: published with a real YouTube id.

    The one definition the scheduler, analyst, insights and costs all
    share — practice uploads carry a `practice-…` id and never left
    this laptop, so their “numbers” must not be reported or learned
    from (their charges still stay in the ledger).
    """
    return (
        VideoStatus(video.status) == VideoStatus.published
        and bool(video.youtube_id)
        and not video.youtube_id.startswith("practice-")  # type: ignore[union-attr]
    )


def latest_snapshot(snaps: list["Snapshot"]) -> "Snapshot | None":
    """A video's current numbers: highest checkpoint, newest row breaks ties."""
    return max(snaps, key=lambda s: (s.checkpoint_hours, s.id or 0)) if snaps else None


class Snapshot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_now)
    video_id: int = Field(foreign_key="video.id")
    checkpoint_hours: int
    views: int = 0
    likes: int = 0
    comments: int = 0
    avg_view_seconds: float | None = None
    avg_view_percent: float | None = None
    shares: int | None = None
    subscribers_gained: int | None = None
