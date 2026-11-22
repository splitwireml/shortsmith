"""Engine, session dependency and table creation. No migrations (v1)."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from app import models  # noqa: F401  registers every table on the metadata
from app.config import Config
from app.models import Settings


def make_engine(config: Config) -> Engine:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{config.db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        get_settings(session)


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
