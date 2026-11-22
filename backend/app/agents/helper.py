"""Helper: help-drawer answers (H6) and “describe it in a sentence” (P3).

`ask` answers only from the help articles it is handed plus a short
summary of the app's current state — the caller (`api/help.py`)
picks the best-matching articles. `suggest` fills a recipe form
from one sentence; the user corrects it before anything is saved.
Both are billed under the `help` stage.
"""

from pydantic_ai import Agent
from sqlmodel import Session

from app.agents.base import run_agent
from app.config import Config
from app.models import PipelineBase, Stage
from app.presets import PRESETS

ask_agent: Agent[None, str] = Agent(
    output_type=str,
    instructions=(
        "You help the owner of this app in plain, friendly words. Answer "
        "only from the help articles and the short summary of their app "
        "below — never invent buttons, screens or steps. If the articles "
        "do not cover the question, say so briefly and point to the "
        "closest article. Keep the answer short: a few sentences, no "
        "jargon, no lists unless steps are needed."
    ),
)

suggest_agent: Agent[None, PipelineBase] = Agent(
    output_type=PipelineBase,
    instructions=(
        "You fill in a recipe form for a YouTube Shorts channel from the "
        "owner's one-sentence description. Fill every field with a "
        "sensible, specific value: a short name, the topic, the goal, "
        "who it is for, region and language notes, genre and tone, art "
        "style, a length of 15 to 60 seconds, how often to post, manual "
        "approval unless they ask otherwise, private visibility unless "
        "they ask otherwise, and any extra notes worth keeping."
    ),
)


def ask_prompt(question: str, articles: list[dict], state_summary: str) -> str:
    lines = [f"Question: {question}", "", "Help articles:"]
    for article in articles:
        lines += ["", f"## {article.get('title', '')}", str(article.get("body", ""))]
    if not articles:
        lines.append("(no articles matched)")
    lines += ["", "The app right now:", state_summary]
    return "\n".join(lines)


async def ask(
    session: Session,
    config: Config,
    *,
    question: str,
    articles: list[dict],
    state_summary: str,
) -> str:
    return await run_agent(
        ask_agent,
        ask_prompt(question, articles, state_summary),
        stage=Stage.help,
        session=session,
        config=config,
        reason="Answered a help question",
    )


async def suggest(session: Session, config: Config, description: str) -> PipelineBase:
    preset_names = ", ".join(p["name"] for p in PRESETS)
    prompt = (
        f"The owner describes their channel in one sentence: “{description}”\n\n"
        f"Existing starter recipes, for the level of detail expected: {preset_names}.\n"
        "Fill in the whole recipe form for the channel described above."
    )
    return await run_agent(
        suggest_agent,
        prompt,
        stage=Stage.help,
        session=session,
        config=config,
        reason="Filled in a recipe from a description",
    )
