import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import models as ai_models
from sqlmodel import Session

os.environ["PYDANTIC_AI_NO_BANNER"] = "1"
ai_models.ALLOW_MODEL_REQUESTS = False  # a real text-model request raises instead of costing money

REPO = Path(__file__).resolve().parents[2]
FAKE_GEMINI_KEY = "test-gemini-key-must-never-leak"

# Hard guard: no test may read the owner's secrets or real data, or reach the network.
_FORBIDDEN = [os.path.normpath(REPO / name) for name in (".env", "credentials.json", "data")]
_LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1", b"localhost", b"127.0.0.1"}


def _forbidden(path) -> bool:
    if isinstance(path, int) or path is None:
        return False
    p = os.path.normpath(os.path.abspath(os.fsdecode(path)))
    return any(p == f or p.startswith(f + os.sep) for f in _FORBIDDEN)


def _guard(event: str, args: tuple) -> None:
    if event in ("open", "sqlite3.connect") and args and _forbidden(args[0]):
        raise PermissionError(f"Test touched a real secret/data path: {args[0]}")
    if event == "socket.getaddrinfo" and args[0] not in _LOCAL_HOSTS:
        raise ConnectionError(f"Test tried to reach the network: {args[0]}")
    if event == "socket.connect" and isinstance(args[1], tuple) and args[1][0] not in _LOCAL_HOSTS:
        raise ConnectionError(f"Test tried to reach the network: {args[1]}")


sys.addaudithook(_guard)


def make_config(data_dir: Path, gemini_api_key: str = FAKE_GEMINI_KEY):
    from app.config import Config

    # Doc is silent on Config's shape: pydantic-settings class `Config` with these two fields.
    return Config(_env_file=None, gemini_api_key=gemini_api_key, data_dir=data_dir)


@pytest.fixture
def config(tmp_path):
    return make_config(tmp_path)


@pytest.fixture
def client(config):
    from app.main import create_app  # doc is silent: app factory taking the Config

    with TestClient(create_app(config)) as c:
        yield c


@pytest.fixture
def session(config):
    """A session on the app's database, set up the way the app sets it up."""
    from app.db import init_db, make_engine

    engine = make_engine(config)
    init_db(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()
