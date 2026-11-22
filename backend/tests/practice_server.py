"""Dev server for UI walkthroughs: the real app, entirely in practice mode.

    cd backend && uv run python tests/practice_server.py

Runs on 127.0.0.1:8484 with a throwaway temp data folder, a fake Gemini
key, practice mode on, and the planner/reviewer replaced by the scripted
fakes in this folder. It never reads `.env` or the real `data/` folder
and never spends money. Temporary files are left in the temp folder it
prints, for inspection after it stops.
"""

import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

# Run as a plain script, sys.path starts in tests/; the app lives beside it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def create_practice_app():
    """The app on a temp folder with a fake key. Importing this runs nothing."""
    from sqlmodel import Session

    from app import media
    from app.config import Config
    from app.db import get_settings
    from app.main import create_app

    data_dir = Path(tempfile.mkdtemp(prefix="shortsmith-practice-"))
    config = Config(
        _env_file=None,  # never the owner's .env
        gemini_api_key="practice-fake-key-not-real",
        data_dir=data_dir,
    )
    app = create_app(config)
    with Session(app.state.engine) as session:
        settings = get_settings(session)
        settings.practice_mode = True
        session.add(settings)
        session.commit()
    # The fake key cannot pass a real lookup; the system check says it works.
    media.check_key = lambda config: True
    print(f"Practice data folder: {data_dir}")
    return app


def main() -> None:
    import uvicorn

    from fakes import fake_text_agents

    with ExitStack() as stack:
        stack.enter_context(fake_text_agents())
        app = create_practice_app()
        print("Practice server: http://127.0.0.1:8484 (Ctrl-C to stop)")
        uvicorn.run(app, host="127.0.0.1", port=8484)


if __name__ == "__main__":
    main()
