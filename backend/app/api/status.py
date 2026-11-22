"""System check for the home page (H2): four checks, plain-language fixes.

The Gemini check only proves a key is configured; a live check arrives
with the first real media call in S2. The YouTube check only looks for
the token file — its contents are a secret and are never read here.
"""

import shutil

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.db import get_session, get_settings

router = APIRouter()

# Below this there is no room to keep making videos comfortably.
MIN_FREE_BYTES = 1_000_000_000


@router.get("/status")
def status(request: Request, session: Session = Depends(get_session)) -> dict:
    config = request.app.state.config
    settings = get_settings(session)

    gemini_ok = bool(config.gemini_api_key.get_secret_value())
    youtube_ok = config.youtube_token_path.is_file()
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    free = shutil.disk_usage(config.data_dir).free
    disk_ok = free >= MIN_FREE_BYTES

    checks = [
        {
            "name": "gemini",
            "ok": gemini_ok,
            "message": (
                "Your Gemini key is set up."
                if gemini_ok
                else "No Gemini API key was found. Add GEMINI_API_KEY to the .env file "
                "in the Shortsmith folder, then restart the app."
            ),
        },
        {
            "name": "youtube",
            "ok": youtube_ok,
            "message": (
                "YouTube is connected."
                if youtube_ok
                else "YouTube is not connected yet. You can connect it when "
                "you are ready to publish."
            ),
        },
        {
            "name": "ffmpeg",
            "ok": ffmpeg_ok,
            "message": (
                "ffmpeg is installed."
                if ffmpeg_ok
                else "ffmpeg was not found. Install it, then restart the app — "
                "Shortsmith needs it to join clips together."
            ),
        },
        {
            "name": "disk",
            "ok": disk_ok,
            "message": (
                f"You have {free / 1e9:.1f} GB of free space."
                if disk_ok
                else f"Only {free / 1e6:.0f} MB of free space is left. "
                "Free up space before making more videos."
            ),
        },
    ]
    return {
        "checks": checks,
        "onboarding_done": settings.onboarding_done,
        "practice_mode": settings.practice_mode,
    }
