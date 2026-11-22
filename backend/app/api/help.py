"""Help: the built-in articles and “Ask the assistant” (H4, H6).

Articles live in `app/help_articles.json` and are re-read on every
request; a missing or unreadable file simply means no articles.
Search in the drawer is the frontend's job — this file only serves
the articles and, for “ask”, picks the few best-matching ones by
plain word overlap to ground the helper's answer.
"""

import asyncio
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from app import costs, youtube
from app.agents import helper
from app.db import get_session, get_settings
from app.models import Pipeline, Video, VideoStatus

router = APIRouter()

ARTICLES_PATH = Path(__file__).resolve().parents[1] / "help_articles.json"
MAX_ARTICLES_FOR_ASK = 5


class AskIn(BaseModel):
    question: str = Field(min_length=1)
    page: str = ""


def load_articles() -> list[dict]:
    try:
        articles = json.loads(ARTICLES_PATH.read_text())
    except (OSError, ValueError):
        return []
    return articles if isinstance(articles, list) else []


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _best_articles(question: str, page: str, articles: list[dict]) -> list[dict]:
    asked = _words(question)
    scored: list[tuple[int, bool, int, dict]] = []
    for index, article in enumerate(articles):
        keywords: set[str] = set()
        for keyword in article.get("keywords") or []:
            keywords |= _words(str(keyword))
        score = (
            3 * len(asked & keywords)
            + 2 * len(asked & _words(str(article.get("title", ""))))
            + len(asked & _words(str(article.get("body", ""))))
        )
        if score:
            scored.append((score, page in (article.get("pages") or []), -index, article))
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    best = [article for _, _, _, article in scored[:MAX_ARTICLES_FOR_ASK]]
    if best:
        return best
    # Nothing matched: the current page's articles are the closest context.
    return [a for a in articles if page in (a.get("pages") or [])][:MAX_ARTICLES_FOR_ASK]


def _state_summary(session: Session, connection: dict) -> str:
    settings = get_settings(session)
    if connection["connected"]:
        youtube_line = "YouTube is connected"
        if connection["channel_title"]:
            youtube_line += f" to the channel “{connection['channel_title']}”"
        youtube_line += "."
    elif connection["needs_reconnect"]:
        youtube_line = "The YouTube sign-in has expired and needs reconnecting."
    else:
        youtube_line = "YouTube is not connected yet."
    videos = session.exec(select(Video)).all()
    waiting = sum(1 for v in videos if v.status == VideoStatus.awaiting_approval)
    published = sum(1 for v in videos if v.status == VideoStatus.published)
    recipes = session.exec(select(Pipeline).where(col(Pipeline.deleted_at).is_(None))).all()
    return "\n".join(
        [
            f"Practice mode is {'on' if settings.practice_mode else 'off'}.",
            f"Monthly budget is ${settings.monthly_budget_usd:.2f}; "
            f"one video may cost up to ${settings.per_video_cap_usd:.2f}.",
            f"There are {len(recipes)} recipes and {len(videos)} videos; "
            f"{waiting} waiting for approval, {published} published.",
            youtube_line,
            f"Old video files are cleaned up after {settings.retention_days} days.",
        ]
    )


@router.get("/help/articles")
def help_articles() -> list[dict]:
    return load_articles()


@router.post("/help/ask")
async def help_ask(
    body: AskIn, request: Request, session: Session = Depends(get_session)
) -> dict:
    config = request.app.state.config
    articles = _best_articles(body.question, body.page, load_articles())
    # The sign-in check is synchronous Google work; keep it off the
    # event loop so one slow lookup cannot stall the whole server.
    connection = await asyncio.to_thread(youtube.status, config)
    try:
        answer = await helper.ask(
            session,
            config,
            question=body.question,
            articles=articles,
            state_summary=_state_summary(session, connection),
        )
    except costs.BudgetExceeded as exc:
        raise HTTPException(402, str(exc)) from None
    return {"answer": answer}
