"""Scripted text-agent outputs, shared by the tests and the practice server for UI walkthroughs.

    with fake_text_agents() as calls:            # planner returns PLAN, reviewer GOOD_REVIEW
        ...run the pipeline...
    calls["planner"][0].prompt                   # everything the planner was shown

No network, no money: the planner and reviewer agents are overridden with Pydantic AI
FunctionModels (docs/research.md §4). Costs are still recorded from the FunctionModel's
estimated token counts, priced as the models named in Settings.
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

# Three 3-second scenes: the shortest clips the video model makes, so practice runs stay fast.
# Each scene prompt carries a unique marker so tests can tell clip calls apart.
PLAN = {
    "title": "Why cats always land on their feet",
    "hook": "Drop a cat upside down. Watch closely.",
    "description": "The righting reflex, explained in 9 seconds.",
    "tags": ["cats", "science", "shorts"],
    "style_bible": "Bright flat cartoon, orange tabby cat, teal background.",
    "thumbnail_prompt": "An orange cartoon cat twisting mid-air, big surprised eyes.",
    "scenes": [
        {"prompt": "SCENE-ONE: a cat falls upside down from a sofa.", "seconds": 3,
         "narration": "Cats fall like this..."},
        {"prompt": "SCENE-TWO: the cat twists its front half, then its back.", "seconds": 3,
         "narration": "...but twist in two halves..."},
        {"prompt": "SCENE-THREE: the cat lands softly on all four paws.", "seconds": 3,
         "narration": "...and land on their feet."},
    ],
}

GOOD_REVIEW = {"score": 9, "summary": "Clear, smooth and on topic.", "bad_clips": []}
OKAY_REVIEW = {"score": 6, "summary": "Fine but forgettable.", "bad_clips": []}
BETTER_PROMPT = "SCENE-THREE-BETTER: the cat lands softly, camera stays still, no cuts."


def flag_clip(index: int, score: int = 5) -> dict:
    """A review naming one bad clip; `index` is Clip.index (0-based, like clip_0.mp4)."""
    return {
        "score": score,
        "summary": f"Clip {index} looks broken.",
        "bad_clips": [{"index": index, "problem": "The cat melts into the floor.",
                       "better_prompt": BETTER_PROMPT}],
    }


@dataclass
class Call:
    messages: list[ModelMessage]
    info: AgentInfo

    @property
    def prompt(self) -> str:
        """All text the model was shown: instructions plus every text part of every request."""
        texts = []
        for message in self.messages:
            if not isinstance(message, ModelRequest):
                continue
            texts.append(message.instructions or "")
            for part in message.parts:
                content = getattr(part, "content", None)
                items = content if isinstance(content, list) else [content]
                texts += [item for item in items if isinstance(item, str)]
        return "\n".join(texts)


def fake_model(*outputs: dict, calls: list[Call] | None = None) -> FunctionModel:
    """Returns outputs[0] on the first call, outputs[1] on the second…, the last one forever after."""
    seen: list[Call] = [] if calls is None else calls

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = outputs[min(len(seen), len(outputs) - 1)]
        seen.append(Call(messages, info))
        if info.output_tools:  # Pydantic AI's default: structured output arrives as a tool call
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])
        return ModelResponse(parts=[TextPart(json.dumps(output))])

    return FunctionModel(respond)


@contextmanager
def fake_text_agents(plan: dict = PLAN, reviews: tuple[dict, ...] = (GOOD_REVIEW,)):
    """Override the planner and reviewer agents; yields the calls each one received."""
    from app.agents import planner, reviewer

    calls: dict[str, list[Call]] = {"planner": [], "reviewer": []}
    with (
        planner.agent.override(model=fake_model(plan, calls=calls["planner"])),
        reviewer.agent.override(model=fake_model(*reviews, calls=calls["reviewer"])),
    ):
        yield calls
