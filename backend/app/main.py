"""The FastAPI app. `create_app(config)` so tests can point it at a
temporary folder; nothing is built at import time, so merely importing
this module never reads `.env` or touches the real data folder.
The lifespan runs start-up recovery (a video left mid-upload becomes
a plain failure) and, unless `Config.run_worker` is off, the worker
loop. When the frontend has been built it is served from the same
process, with every unknown page falling back to its index.html;
unknown API addresses stay JSON 404s.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session
from starlette.responses import Response

from app import db, pipeline, scheduler
from app.api import costs, help, insights, media, pipelines, settings, status, videos, youtube
from app.config import Config

logging.getLogger("httpx").setLevel(logging.WARNING)


def _plain_validation_error(exc: RequestValidationError) -> str:
    # Errors are for the person using the app: one readable sentence.
    parts = []
    for error in exc.errors():
        where = " ".join(str(p) for p in error["loc"] if p != "body")
        parts.append(f"{where}: {error['msg']}" if where else error["msg"])
    return "Please check the form — " + "; ".join(parts) + "."


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config()
    engine = db.make_engine(config)
    db.init_db(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with Session(engine) as session:
            pipeline.recover_publishing(session)
        worker = (
            asyncio.create_task(scheduler.run_worker(config, engine))
            if config.run_worker
            else None
        )
        try:
            yield
        finally:
            if worker is not None:
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
            engine.dispose()

    app = FastAPI(title="Shortsmith", lifespan=lifespan)
    app.state.config = config
    app.state.engine = engine

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _plain_validation_error(exc)})

    for router in (
        pipelines.router,
        videos.router,
        media.router,
        settings.router,
        costs.router,
        status.router,
        youtube.router,
        insights.router,
        help.router,
    ):
        app.include_router(router, prefix="/api")

    # The built frontend (adapter-static) is one index.html plus files
    # under _app/: real files are served as they are and every other
    # page gets index.html, so a link opened directly still works.
    # Registered last, so /api routes win; an unknown /api address
    # reaching here is a JSON 404, never the app page. With no build
    # the app is API only and still starts.
    index = config.frontend_dir / "index.html"
    if index.is_file():
        root = config.frontend_dir.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str) -> Response:
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={"detail": "That address could not be found."},
                )
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8484)
