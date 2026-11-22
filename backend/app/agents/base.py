"""One path for every text-agent call: build the model, run, record the cost.

The agents themselves are module-level objects with no model attached, so
importing them needs no key and tests can override them. Each run passes
the model named in Settings; a test override still wins over that, and the
run is billed as the Settings model either way.
"""

from collections.abc import Sequence
from typing import TypeVar

from pydantic_ai import Agent
from pydantic_ai.messages import UserContent
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider
from sqlmodel import Session

from app import costs, db
from app.config import Config
from app.models import Pipeline, Settings, Stage, Video

OutputT = TypeVar("OutputT")

# Which Settings role pays for each stage.
_ROLE_FOR_STAGE = {
    Stage.planning: "planner",
    Stage.review: "reviewer",
    Stage.analytics: "analyst",
    Stage.help: "helper",
}

# ponytail: flat reserve for one text call. Help and analyst calls cost
# cents and are unknowable in advance, so reserve a nickel and let the
# monthly cap still be a cap (C3). The video stages reserve their own
# upcoming spend in pipeline.py and are not re-checked here.
TEXT_CALL_RESERVE_USD = 0.05
_BUDGET_CHECKED_STAGES = {Stage.analytics, Stage.help}


def build_model(role: str, settings: Settings, config: Config) -> GoogleModel:
    provider = GoogleProvider(api_key=config.gemini_api_key.get_secret_value())
    return GoogleModel(getattr(settings, f"{role}_model"), provider=provider)


async def run_agent(
    agent: Agent[None, OutputT],
    prompt: str | Sequence[UserContent],
    *,
    stage: Stage,
    session: Session,
    config: Config,
    reason: str,
    video: Video | None = None,
    pipeline: Pipeline | None = None,
) -> OutputT:
    """Run one agent call and write its cost event from the usage numbers."""
    settings = db.get_settings(session)
    if stage in _BUDGET_CHECKED_STAGES:
        # No video to charge against: this checks the monthly cap only.
        costs.check_budget(session, None, upcoming_usd=TEXT_CALL_RESERVE_USD)
    role = _ROLE_FOR_STAGE[stage]
    result = await agent.run(
        prompt,
        model=build_model(role, settings, config),
        model_settings=GoogleModelSettings(thinking=getattr(settings, f"{role}_effort")),
    )
    # Pydantic AI's Google mapping already counts thinking tokens in
    # output_tokens (its price extractor sums candidates + thoughts into
    # output_tokens; details["thoughts_tokens"] is the same count again).
    # Thinking is billed as output, so record output_tokens as it stands —
    # adding thoughts_tokens here would charge for them twice.
    costs.record(
        session,
        stage=stage,
        model=getattr(settings, f"{role}_model"),
        reason=reason,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        video=video,
        pipeline=pipeline,
    )
    return result.output
