"""Engine, session dependency and table creation, plus a few hand-added columns."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app import models  # noqa: F401  registers every table on the metadata
from app.config import Config
from app.models import Settings

# Defaults match the model defaults, so old rows read the same as new ones.
_NEW_COLUMNS = {
    "pipeline": {
        "video_resolution": "VARCHAR NOT NULL DEFAULT '1080p'",
        "clip_seconds": "INTEGER NOT NULL DEFAULT 15",
        "clip_buffer_pct": "INTEGER NOT NULL DEFAULT 10",
    },
    "video": {
        "practice": "BOOLEAN NOT NULL DEFAULT 0",
    },
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
    # the columns that arrived after v1 by hand. Switch to a real
    # migration tool if this list keeps growing.
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _NEW_COLUMNS.items():
            have = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        # Free "video" clips mean practice media. Every start-up, not just
        # the first (the ALTER commits before this), and only events from
        # the video's own lifetime: deleted videos leave ids SQLite reuses.
        conn.execute(
            text(
                "UPDATE video SET practice = 1 WHERE practice = 0 AND EXISTS (SELECT 1 FROM costevent "
                "WHERE costevent.video_id = video.id AND stage = 'video' AND cost_usd = 0 "
                "AND costevent.created_at >= video.created_at)"
            )
        )


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
