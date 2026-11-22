"""System check for the home page (H2): four checks, plain-language fixes.

The Gemini check proves the key works with one free lookup (no
generation, no charge). The YouTube check asks `youtube.status()`,
so an expired sign-in shows the plain reconnect message (Y3) —
the token itself is never returned.
"""

import shutil

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app import media, youtube
from app.db import get_session, get_settings

router = APIRouter()

# Below this there is no room to keep making videos comfortably.
MIN_FREE_BYTES = 1_000_000_000


@router.get("/status")
def status(request: Request, session: Session = Depends(get_session)) -> dict:
    config = request.app.state.config
    settings = get_settings(session)

    key_found = bool(config.gemini_api_key.get_secret_value())
    verdict = media.check_key(config) if key_found else False
    gemini_ok = verdict is True
    if gemini_ok:
        gemini_message = "Your Gemini key works."
    elif not key_found:
        gemini_message = (
            "No Gemini API key was found. Add GEMINI_API_KEY to the .env file "
            "in the Shortsmith folder, then restart the app."
        )
    elif verdict is None:
        gemini_message = (
            "We could not check your Gemini key just now because Google did "
            "not answer. Check your internet connection and try again."
        )
    else:
        gemini_message = (
            "A Gemini key was found, but Google did not accept it. Check the "
            "key in the .env file in the Shortsmith folder, then restart the app."
        )
    connection = youtube.status(config)
    youtube_ok = connection["connected"]
    if youtube_ok:
        youtube_message = (
            f"YouTube is connected to {connection['channel_title']}."
            if connection["channel_title"]
            else "YouTube is connected."
        )
    elif connection["needs_reconnect"]:
        youtube_message = (
            "Your YouTube sign-in has expired. Press Connect YouTube to "
            "sign in again — until then, videos cannot be published."
        )
    else:
        youtube_message = (
            "YouTube is not connected yet. You can connect it when "
            "you are ready to publish."
        )
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    free = shutil.disk_usage(config.data_dir).free
    disk_ok = free >= MIN_FREE_BYTES

    checks = [
        {"name": "gemini", "ok": gemini_ok, "message": gemini_message},
        {"name": "youtube", "ok": youtube_ok, "message": youtube_message},
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
