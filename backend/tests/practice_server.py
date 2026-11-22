"""Dev server for UI walkthroughs: the real app, entirely in practice mode.

    cd backend && uv run python tests/practice_server.py

Runs on 127.0.0.1:8484 with a throwaway temp data folder, a fake Gemini
key, practice mode on, and every text agent (planner, reviewer, analyst,
helper) replaced by the scripted fakes in this folder — so a whole UI
walkthrough, help “ask” and recipe suggestion included, never makes a
real call. It never reads `.env` or the real `data/` folder and never
spends money. Temporary files are left in the temp folder it prints, for
inspection after it stops.
"""

# What “Describe it in a sentence” fills in on the practice server.
SUGGESTION = {
    "name": "Practice cats",
    "niche": "Cute and surprising things cats do",
    "objective": "Delight viewers with one charming cat moment per video",
    "audience": "Cat lovers of all ages",
    "region_notes": "Plain international English",
    "genre": "Feel-good animal stories",
    "art_style": "Soft, friendly cartoon cats in bright colours",
    "target_seconds": 25,
    "every_days": 1,
    "videos_per_run": 1,
    "approval_mode": "manual",
    "auto_approve_score": 8,
    "visibility": "private",
    "extra_notes": "One cat hero, a tiny problem, and a happy ending.",
}

PRACTICE_ANSWER = (
    "This is a scripted practice answer, so no AI was called. In the real "
    "app the assistant answers from the help articles — try the search "
    "above for the article that covers your question."
)

PRACTICE_ANALYSIS = {
    "lessons_to_add": ["Practice runs: open with the surprising moment in the first two seconds."],
    "lesson_ids_to_retire": [],
}

import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

# Run as a plain script, sys.path starts in tests/; the app lives beside it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _stub_youtube() -> None:
    """Replace every YouTube entry point with in-memory answers.

    Clicking “Connect YouTube” in a walkthrough must never open a
    real Google sign-in (the real connect uses the repo's OAuth
    client file). The upload stub ignores the practice flag, so
    even switching practice mode off in Settings cannot reach
    YouTube from here; media generation is the app's own practice
    path, which the seeded Settings below turn on.
    """
    import uuid

    from app import youtube

    state = {"connected": False}

    def connect(_config) -> None:
        state["connected"] = True

    def disconnect(_config) -> None:
        state["connected"] = False

    def status(_config) -> dict:
        return {
            "connected": state["connected"],
            "channel_title": "Practice Channel" if state["connected"] else None,
            "needs_reconnect": False,
        }

    youtube.connect = connect
    youtube.disconnect = disconnect
    youtube.status = status
    youtube.upload = lambda _config, **_kw: f"practice-{uuid.uuid4().hex[:8]}"
    youtube.set_thumbnail = lambda _config, _youtube_id, _path: None
    youtube.fetch_stats = lambda _config, _youtube_id, *, with_analytics: {
        "views": 0, "likes": 0, "comments": 0,
    }


def create_practice_app():
    """The app on a temp folder with a fake key. Importing this runs nothing."""
    from sqlmodel import Session

    from app import media
    from app.config import Config
    from app.db import get_settings
    from app.main import create_app

    _stub_youtube()

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
    # Media stays on the practice path even if practice mode is
    # switched off in Settings during the walkthrough.
    real_clip, real_thumbnail = media.generate_clip, media.generate_thumbnail

    async def practice_clip(prompt, seconds, *, settings, **kw):
        return await real_clip(
            prompt, seconds, settings=settings.model_copy(update={"practice_mode": True}), **kw
        )

    async def practice_thumbnail(prompt, *, settings, **kw):
        return await real_thumbnail(
            prompt, settings=settings.model_copy(update={"practice_mode": True}), **kw
        )

    media.generate_clip = practice_clip
    media.generate_thumbnail = practice_thumbnail
    print(f"Practice data folder: {data_dir}")
    return app


def main() -> None:
    import uvicorn

    from app.agents import helper
    from fakes import fake_analyst, fake_helper, fake_model, fake_text_agents

    with ExitStack() as stack:
        stack.enter_context(fake_text_agents())
        stack.enter_context(fake_analyst(PRACTICE_ANALYSIS))
        stack.enter_context(fake_helper(PRACTICE_ANSWER))
        stack.enter_context(helper.suggest_agent.override(model=fake_model(SUGGESTION)))
        app = create_practice_app()
        print("Practice server: http://127.0.0.1:8484 (Ctrl-C to stop)")
        uvicorn.run(app, host="127.0.0.1", port=8484)


if __name__ == "__main__":
    main()
