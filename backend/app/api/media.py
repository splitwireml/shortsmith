"""Serve one stored file (clip, finished video, thumbnail) to the browser.

The key comes from the URL, so it goes through Storage, which refuses
anything outside the media folder.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.storage import Storage

router = APIRouter()


@router.get("/media/{key:path}")
def get_media(key: str, request: Request) -> FileResponse:
    storage = Storage(request.app.state.config.media_dir)
    try:
        path = storage.path(key)
    except ValueError:
        raise HTTPException(404, "That file could not be found.") from None
    if not path.is_file():
        raise HTTPException(404, "That file could not be found. It may have been cleaned up.")
    return FileResponse(path)
