"""YouTube connection: status, Connect, Disconnect (Y1, Y3).

`connect` only starts the browser sign-in in the background and
answers at once with the current status; the UI polls
`/youtube/status` until `connected` turns true. No answer ever
contains a token.
"""

from fastapi import APIRouter, HTTPException, Request

from app import youtube

router = APIRouter()


@router.get("/youtube/status")
def youtube_status(request: Request) -> dict:
    return youtube.status(request.app.state.config)


@router.post("/youtube/connect")
def youtube_connect(request: Request) -> dict:
    config = request.app.state.config
    try:
        youtube.connect(config)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from None
    return youtube.status(config)


@router.post("/youtube/disconnect")
def youtube_disconnect(request: Request) -> dict:
    config = request.app.state.config
    youtube.disconnect(config)
    return youtube.status(config)
