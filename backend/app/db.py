"""Engine, session dependency and table creation, plus a few hand-added columns."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app import models  # noqa: F401  registers every table on the metadata
from app.config import Config
from app.models import Settings

# Defaults match PipelineBase, so old recipes read the same as new ones.
_NEW_PIPELINE_COLUMNS = {
    "video_resolution": "VARCHAR NOT NULL DEFAULT '1080p'",
    "clip_seconds": "INTEGER NOT NULL DEFAULT 15",
    "clip_buffer_pct": "INTEGER NOT NULL DEFAULT 10",
}


def make_engine(config: Config) -> Engine:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{config.db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    # ponytail: create_all never adds columns to an existing table, so add
    # the recipe columns that arrived after v1 by hand. Switch to a real
    # migration tool if this list keeps growing.
    have = {c["name"] for c in inspect(engine).get_columns("pipeline")}
    with engine.begin() as conn:
        for name, ddl in _NEW_PIPELINE_COLUMNS.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE pipeline ADD COLUMN {name} {ddl}"))


def get_settings(session: Session) -> Settings:
    """The one Settings row, created with the defaults the first time."""
    settings = session.exec(select(Settings)).first()
    if settings is None:
        settings = Settings()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
