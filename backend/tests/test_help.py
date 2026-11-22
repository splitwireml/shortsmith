"""S3 help: the articles route and "Ask the assistant" (H6).

These tests bring their own articles; the real help_articles.json belongs to another sprint.
Interface choices where docs/02-architecture.md is silent: `app.api.help.load_articles()` returns
the article list and is called on every request (so it can be swapped here); `helper.ask_agent`
answers in plain text (output type `str`).
"""

import re

from sqlmodel import select

from app.api import help as help_api
from app.models import CostEvent
from conftest import FAKE_GEMINI_KEY
from fakes import fake_helper


def article(id_: str, title: str, body: str, page: str, keywords: list[str]) -> dict:
    return {"id": id_, "title": title, "body": f"{body} BODY-{id_.upper()}", "pages": [page],
            "keywords": keywords}


ARTICLES = [
    article("budget", "Set your monthly budget", "Open Settings and type a new amount in "
            "Monthly budget. The app stops before going over it.", "/settings",
            ["budget", "money", "limit", "spend", "monthly"]),
    article("youtube", "Connect YouTube", "Press Connect YouTube and sign in with Google.",
            "/setup", ["youtube", "channel", "sign in"]),
    article("practice", "Practice mode", "Practice mode makes free test videos and never uploads.",
            "/settings", ["practice", "test", "free"]),
    article("approve", "Approve a video", "Watch the video, then press Approve or Reject.",
            "/videos", ["approve", "reject", "inbox"]),
    article("retry", "When a video fails", "Read the reason on the video page, then press Retry.",
            "/videos", ["failed", "error", "retry"]),
    article("lessons", "What lessons are", "Lessons are short notes the planner follows.",
            "/insights", ["lessons", "learning", "insights"]),
    article("storage", "Disk space", "Old video files are deleted after the days you choose.",
            "/settings", ["disk", "storage", "space", "delete"]),
]
ANSWER = "Open Settings and type a new amount in Monthly budget."


def test_ask_answers_from_the_best_articles_and_records_help_cost(client, session, monkeypatch):
    monkeypatch.setattr(help_api, "load_articles", lambda: ARTICLES)
    assert client.get("/api/help/articles").json() == ARTICLES

    question = "How do I change my monthly budget?"
    with fake_helper(ANSWER) as calls:
        asked = client.post("/api/help/ask", json={"question": question, "page": "/settings"})

    assert asked.status_code == 200, asked.text
    assert asked.json() == {"answer": ANSWER}
    [ask] = calls
    assert question in ask.prompt
    assert "BODY-BUDGET" in ask.prompt  # grounded in the article that answers it
    assert len(re.findall(r"BODY-[A-Z]+", ask.prompt)) <= 5  # the best matches, not all seven
    assert FAKE_GEMINI_KEY not in ask.prompt
    events = session.exec(select(CostEvent)).all()
    assert [(e.stage, e.model, e.video_id) for e in events] == [("help", "gemini-4-hydrogen", None)]
    assert events[0].cost_usd > 0


def test_ask_stops_at_the_monthly_budget(client, session, monkeypatch):
    # Review S3 #3: help is a paid call, so the monthly cap covers it (C3).
    from app.db import get_settings

    monkeypatch.setattr(help_api, "load_articles", lambda: ARTICLES)
    settings = get_settings(session)
    settings.monthly_budget_usd = 0
    session.add(settings)
    session.commit()

    with fake_helper(ANSWER) as calls:
        asked = client.post("/api/help/ask", json={"question": "budget?", "page": "/settings"})

    assert asked.status_code == 402, asked.text
    assert "budget" in asked.json()["detail"]
    assert calls == []  # nothing was spent
