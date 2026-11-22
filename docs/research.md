# API research (verified 2026-11-22)

Sources: official docs fetched today + source of installed packages (`uv run --with`). No paid calls were made.
`ai.google.dev/gemini-api/docs/*` now 301-redirects to `aistudio.google.com/docs/*` (append `.md` for raw markdown).
"UNCONFIRMED" = docs silent/contradictory, or not testable without a paid call. Do not guess around these.

## 0. Corrections to our starting assumptions (read first)

| Assumption | What the docs say today |
|---|---|
| Video gen is under `generateContent` | Omni is documented **only** on the Interactions API: `client.interactions.create(...)`. The docs index has no `(generateContent)` variant of the Omni page. Omni via `generateContent` = UNCONFIRMED. [omni](https://aistudio.google.com/docs/omni.md), [llms.txt](https://aistudio.google.com/llms.txt) |
| Model ID `gemini-omni-flash-preview` | Listed as **"Shut down"**. Stable IDs: `gemini-omni-1.2-flash` (current), `gemini-omni-1.1-flash` (routes to 1.2 on 2026-12-03). [model page](https://aistudio.google.com/docs/models/gemini-omni-flash.md) |
| Unaudited API projects upload as private only | **Reversed 2026-11-02.** [revision history](https://developers.google.com/youtube/v3/revision_history) |
| `videos.insert` costs 1600 units | Now **1 unit in its own bucket, 100 calls/day**. [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert) |
| No custom thumbnails for Shorts via API | `thumbnails.set` supports Shorts since **2026-11-03**. [thumbnails.set](https://developers.google.com/youtube/v3/docs/thumbnails/set) |
| Latest google-genai everywhere | `pydantic-ai-slim[google]==2.71.0` pins `google-genai<3,>=2.30.0`; PyPI latest is 3.6.1. A shared venv resolves to 2.34.x (verified: it has `client.interactions` and the video `response_format`). |

**Confirmed 2026-11-22** with the free call `client.models.get(...)` on our key: `gemini-omni-1.2-flash` resolves (so do `gemini-nano-banana-2.1`, `gemini-4-hydrogen`, `gemini-4-argon`). Use `gemini-omni-1.2-flash`; never the preview ID.

**Live calls during the build (2026-11-22, through the app, recorded in its ledger):** planner via Pydantic AI on `gemini-4-hydrogen` (high) with structured output works — 494 in / 1,960 out tokens, $0.0154, 15 s. Thumbnail `gemini-nano-banana-2.1` via Interactions (9:16, 1K, no `delivery` key) works, $0.0336. Omni `gemini-omni-1.2-flash` 3 s 720p 9:16 clip via Interactions with `delivery: "uri"` + Files download works, $0.2085; thumbnail + clip + download + stitch took 59 s together. Review on `gemini-4-argon` (high) of the 3 s stitched video sent inline works: 929 in / 381 out tokens, $0.0113, 15 s — its note: the planned narration line was longer than the clip and got cut off (keep narration to roughly 2 words per second of clip).

## 1. Video generation: Gemini Omni 1.2 Flash

From [omni](https://aistudio.google.com/docs/omni.md) unless noted.

- Interactions API is GA (June 2026) and "the recommended interface for all new projects"; `generateContent` is "legacy" but supported for text/image models. Needs `google-genai>=2.3.0`. [interactions](https://aistudio.google.com/docs/interactions-overview.md)
- Not `generate_videos`: Veo 3.1 preview was shut down in the Gemini API on 2026-10-22. [video](https://aistudio.google.com/docs/video.md)
- Output: MP4, 24 FPS, synchronized **native audio** (speech, SFX, music), SynthID watermark. No audio on/off parameter — steer in the prompt ("No dialogue", "Include calm background music"). English fully supported; other languages "not evaluated".

```python
import base64
from google import genai

client = genai.Client(api_key=API_KEY)
interaction = client.interactions.create(      # async: await client.aio.interactions.create(...)
    model="gemini-omni-1.2-flash",
    input="Continuous handheld shot of ... Sound design: ... No dialogue.",
    response_format={
        "type": "video",
        "aspect_ratio": "9:16",   # "16:9" (default) | "9:16" — only these two
        "duration": "15s",        # whole seconds "3s".."15s", default "10s"; >15s = invalid argument
        "resolution": "720p",     # "360p" | "720p" (default) | "1080p" (upscaled) | "4k" (upscaled)
        # "delivery": "uri",      # "inline" (default) | "uri"
    },
)
open("clip.mp4", "wb").write(base64.b64decode(interaction.output_video.data))
```

- **Return shape**: plain request/response (`duration` overrides any length written in the prompt). Default is inline base64 at `interaction.output_video.data` (SDK convenience; raw REST: the `steps[].content[]` item with `type: "video"`).
- **Above 4 MB use `delivery: "uri"`**: take `output_video.uri`, poll `client.files.get(name=f"files/{id}")` until `state.name == "ACTIVE"` (`"FAILED"` = error), then `client.files.download(file=output_video.uri, destination="out.mp4")`.
- Docs' speed tip: `background=False, store=False, stream=False`. `store=False` disables `previous_interaction_id` follow-ups. Stored interactions are kept 55 days on paid tier.
- **Latency: UNCONFIRMED** — docs only say it grows with duration, resolution and load. Docs note standard HTTP requests "typically close after 60 seconds"; the background-execution page does not list Omni, so `background=True` for Omni is UNCONFIRMED. Use a long client timeout and measure. [background](https://aistudio.google.com/docs/background-execution.md)

Inputs and cross-clip consistency:

- Parts: `{"type": "image", "data": b64, "mime_type": "image/png"}` or `{"type": "image", "uri": file.uri}`; `{"type": "video", "uri": file.uri}` (Files API); `{"type": "text", "text": "..."}`.
- **Subject reference**: up to 6 reference images per request (≤3 per character, ≤2 characters) for likeness/attire/objects. Valid for generate, edit and extend.
- **Reference videos**: new generation only; 3–10 s outputs take up to 3 (≤3 s each), 11–15 s outputs take 1; their audio is ignored.
- **First + last frame**: two images + transition prompt; 3–10 s only.
- **Extension**: prompt "Continue the scene: ..." with `previous_interaction_id=prev.id`, or with an uploaded video part. Adds 3–10 s per turn (default 10), sees only the **last 10 s**, **max 30 s total**, append-only. Re-describe or re-reference anything older than the last 10 s.
- **Edit**: `previous_interaction_id` + short instruction ("... Keep everything else the same"); input ≤15 s.
- Describe each input's role in plain language. `generation_config={"video_config": {"task": "image_to_video"}}` (`text_to_video|image_to_video|reference_to_video|edit|extend`) is a fallback only. Tags like `<FIRST_FRAME>` are deprecated.
- Omni cuts between shots by default; ask for "a single continuous shot, no scene cuts". Timecodes work (`[0-5s] ... [5-10s] ...`). On-screen text can be prompted.
- Not supported: system instructions, temperature/top_p, stop sequences, negative-prompt param, audio inputs, voice editing, YouTube URLs as source. Editing/extending **uploaded** videos is unavailable in EEA/CH/UK (model-generated videos are fine).

Implication: one call yields ≤15 s (≤30 s via extension). A 60 s Short needs ≥4 clips or 2 extended chains, stitched locally.

Pricing ([pricing](https://aistudio.google.com/docs/pricing.md#gemini-omni-1.2-flash)) — paid tier only: input $1.50 / 1M tokens; output $9.00 / 1M (text), **$12.00 / 1M (video)**. Video output tokens per second: 360p 1,931 · **720p 5,792** · 1080p 8,688 · 4K 17,376.

| Resolution | $/s | 30 s | 60 s |
|---|---|---|---|
| 360p | $0.023 | $0.70 | $1.39 |
| 720p | $0.070 | $2.09 | $4.17 |
| 1080p (upscaled) | $0.104 | $3.13 | $6.26 |

Arithmetic from the published rates; excludes retries, input and thinking tokens. Whether an extension turn bills only the new seconds or the whole returned video is UNCONFIRMED.

Rate limits ([rate-limits](https://aistudio.google.com/docs/rate-limits.md#gemini-omni-flash-rate-limits)): Tier 1 **8 RPM / 40 RPD**; Tier 2 16 / 200; Tier 3 40 / 2,000; per project, RPD resets midnight Pacific. Tier 1 also has a $10 per rolling-10-minutes spend limit (429 `RESOURCE_EXHAUSTED`) and a $250 billing cap. 40 RPD ≈ ten 60 s Shorts/day with zero retries.

## 2. Image generation (thumbnails)

| ID | Name | Note | Price per image (Standard) |
|---|---|---|---|
| `gemini-nano-banana-2.1` | Nano Banana 2.1 | Current workhorse; docs recommend it for new projects | $0.0336 (1K), $0.0504 (2K), $0.113 (4K) |
| `gemini-3.1-flash-image` | Nano Banana 2 | Previous generation | $0.045 (0.5K), $0.067 (1K), $0.101 (2K), $0.151 (4K) |
| `gemini-3-pro-image` | Nano Banana Pro | Premium; best text rendering and complex layouts | $0.134 (1K/2K), $0.24 (4K) |
| `gemini-3.1-flash-lite-image` | Nano Banana 2 Lite | Cheapest/fastest; weak at multi-reference and multi-turn | $0.0336 (1K) |

Sources: [image-generation](https://aistudio.google.com/docs/image-generation.md), [pricing](https://aistudio.google.com/docs/pricing.md). Batch is 50% off. No free tier for 2.1.

```python
interaction = client.interactions.create(
    model="gemini-nano-banana-2.1",
    input=prompt,  # or a list with {"type": "image", ...} reference parts
    response_format={"type": "image", "aspect_ratio": "9:16", "image_size": "2K"},
)
png = base64.b64decode(interaction.output_image.data)
```

- **Verified live 2026-11-22:** do not send a `delivery` key for images — `"delivery": "inline"` gets `400 invalid_request: "Image delivery mode is not supported."` Inline base64 is the only (default) image delivery.
- Legacy equivalent: `client.models.generate_content(model=..., contents=[prompt], config=types.GenerateContentConfig(image_config=types.ImageConfig(aspect_ratio="9:16", image_size="2K")))`, then `part.as_image()` for each part in `response.parts` with `inline_data`.
- `aspect_ratio` includes `"9:16"` and `"16:9"` (also 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 21:9, 1:4, 4:1, 1:8, 8:1). Default: 1:1 or the input image's ratio.
- `image_size`: `"1K" | "2K" | "4K"`, uppercase K required. 2.1 sizes: 9:16 = 768x1376 / 1536x2752 / 3072x5504; 16:9 = 1376x768 / 2752x1536 / 5504x3072.
- Accepts image and video inputs, so a frame or the clip can seed the thumbnail. Consistency up to 4 characters / 10 objects on 2.1. Docs tip: generate the text first, then ask for an image containing it.

## 3. Text models: gemini-4-hydrogen and gemini-4-argon

| | `gemini-4-hydrogen` | `gemini-4-argon` |
|---|---|---|
| Positioning | "Fast", cost-efficient everyday coding/agent/multimodal model | "Efficient frontier reasoning model": Gemini 4 intelligence, fewer thinking tokens than Carbon |
| Input / output per 1M (Standard) | **$1.50 / $7.50** | $2.00 / $10.00 through 2026-11-30, **$4.00 / $20.00 from 2026-12-01** |
| Free tier | Yes | No |
| Thinking levels | `low`, `medium`, `high` (default), `xhigh` | `low`, `medium` (default), `high` |
| Non-streaming output cap per call | 65,536 | 32,768 |

Sources: [choosing-a-model](https://aistudio.google.com/docs/choosing-a-model.md), [pricing](https://aistudio.google.com/docs/pricing.md), [thinking](https://aistudio.google.com/docs/thinking.md), [hydrogen](https://aistudio.google.com/docs/models/gemini-4-hydrogen.md), [argon](https://aistudio.google.com/docs/models/gemini-4-argon.md).

- Hydrogen is cheaper. Argon is priced like Carbon and positioned as the deeper reasoner, but docs publish no Hydrogen-vs-Argon benchmark — "Argon is smarter" is positioning, not a measured claim.
- Both: 1,048,576-token window shared by input + thinking + output; text/image/video/audio/PDF in, text out; structured outputs and function calling supported; Batch/Flex 50% off; implicit caching only.
- Output price includes thinking tokens. One input rate for all modalities (no separate video rate). **Remove `temperature`, `top_p`, `top_k`** on Gemini 4 (ignored in range, 400 out of range). `minimal` thinking is rejected. [whats-new](https://aistudio.google.com/docs/whats-new-gemini-4-hydrogen.md)
- Thinking parameter is `thinking_level`. Interactions: `generation_config={"thinking_level": "low"}`. generateContent: `config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low"))`. A small `max_output_tokens` can truncate mid-thinking; lower the level instead.
- Structured output ([structured-output](https://aistudio.google.com/docs/structured-output.md)). Interactions: `response_format={"type": "text", "mime_type": "application/json", "schema": M.model_json_schema()}` → `M.model_validate_json(interaction.output_text)`. generateContent: `config={"response_mime_type": "application/json", "response_json_schema": M.model_json_schema()}` → `response.text`. `minLength/maxLength/uniqueItems` are silently stripped; validate client-side.
- Usage: `interaction.usage.total_input_tokens / total_output_tokens / total_thought_tokens`; generateContent `response.usage_metadata.prompt_token_count / candidates_token_count / thoughts_token_count`.

Video input for review ([video-understanding](https://aistudio.google.com/docs/video-understanding.md), [tokens](https://aistudio.google.com/docs/tokens.md)):

- Default static mode: 1 FPS frames + audio. **~100 tokens/s at default (low) media resolution, ~300 tokens/s at high** (66 or 258 per frame + 32/s audio). 60 s ≈ 6,000 tokens ≈ $0.009 on Hydrogen. One bullet on the tokens page says "263 tokens per second" — inconsistent; read `usage`.
- 1 FPS can miss fast action. Agentic mode (`"processing": "agentic"`) only pays off above ~5 minutes; keep static.
- **Inline bytes**: prose says "under 20MB total request size", the table on the same page says "< 100MB" — treat **20 MB** as the limit.
- **Files API** ([files](https://aistudio.google.com/docs/files.md)): `f = client.files.upload(file="clip.mp4")`; poll `client.files.get(name=f.name)` until `f.state.name == "ACTIVE"`; pass `{"type": "video", "uri": f.uri, "mime_type": f.mime_type}` (Interactions) or `contents=[f, "prompt"]` (generateContent). Free, kept 48 h, 20 GB per project.
- Put the text prompt after the video part; refer to moments as `MM:SS`.

## 4. Pydantic AI

Latest: **pydantic-ai 2.71.0** (PyPI, 2026-11-19, Python ≥3.11). Docs moved to `pydantic.dev/docs/ai/`. Everything below was executed offline against 2.71.0.

```python
from pathlib import Path
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent, UploadedFile
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider

class Review(BaseModel):
    score: int
    notes: str
provider = GoogleProvider(api_key=API_KEY)                  # explicit key
model = GoogleModel("gemini-4-hydrogen", provider=provider)
agent = Agent(model, output_type=Review, instructions="Review the clip.",
              model_settings=GoogleModelSettings(thinking="medium"))  # unified effort setting
clip = BinaryContent(data=Path("clip.mp4").read_bytes(), media_type="video/mp4")
result = await agent.run(["Review this Short.", clip])     # or agent.run_sync(...)
result.output      # Review instance
result.usage       # RunUsage — a PROPERTY in 2.x, not a method
result.usage.input_tokens, result.usage.output_tokens, result.usage.requests, result.usage.cost
```

- `thinking`: `True/False | "minimal" | "low" | "medium" | "high" | "xhigh" | "max"`; for Google it becomes `thinking_level`, snapped to the model's supported set (built-in profiles: hydrogen LOW–XHIGH, argon LOW–HIGH). Alternatives: `capabilities=[Thinking(effort="medium")]` (`pydantic_ai.capabilities`) or native `google_thinking_config={"thinking_level": ...}`. [google docs](https://pydantic.dev/docs/ai/models/google/)
- Do not set `temperature`/`top_p` for Gemini 4 (§3).
- Video input ([input docs](https://pydantic.dev/docs/ai/advanced-features/input/)): `BinaryContent` is sent inline (20 MB request limit). For the Files API: `f = await provider.client.aio.files.upload(file="clip.mp4")`, wait for `ACTIVE`, then `UploadedFile(file_id=f.uri, media_type=f.mime_type, provider_name=model.system)` (`model.system == "google"`). `VideoUrl` on the Gemini API only works for YouTube and Files API URLs.
- `provider.client` is the underlying `google.genai.Client` — reuse it for `client.interactions.create(...)` media calls. First run prints a banner; silence with `PYDANTIC_AI_NO_BANNER=1`.

Testing without network ([testing docs](https://pydantic.dev/docs/ai/guides/testing/)):

```python
from pydantic_ai import ModelMessage, ModelResponse, ToolCallPart, models
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import AgentInfo, FunctionModel

models.ALLOW_MODEL_REQUESTS = False            # real calls raise RuntimeError
with agent.override(model=TestModel()):        # schema-valid dummy: Review(score=0, notes='a')
    r = agent.run_sync("x")
def fake(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"score": 7, "notes": "ok"})])
with agent.override(model=FunctionModel(fake)):  # exact scripted output
    r = agent.run_sync("x")
```

Structured output arrives as a tool call named `final_result`. `capture_run_messages()` records the exchange. Use pytest + anyio for async tests.

Media generation and prices:

- **Images: yes.** `from pydantic_ai.images import ImageGenerator`; `r = await ImageGenerator("google:gemini-3-pro-image").generate(prompt, settings={"aspect_ratio": "9:16"})` (or `.generate_sync`) → `r.images[0].content.data` (bytes), `r.usage`. Size via `GoogleImageGenerationSettings(google_image_config={"image_size": "2K"})` from `pydantic_ai.images.google`. Known names: `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`. `gemini-nano-banana-2.1` is not in the list; the model object constructs, a live call is UNCONFIRMED. `TestImageGenerationModel` exists for tests.
- **Video: no.** Nothing for video generation or Omni in the 2.71.0 package — call google-genai directly.
- **Prices**: depends on `genai-prices>=0.2.3` (0.2.5 installed); `RunUsage.cost` is a best-effort USD `Decimal | None`. 0.2.5 knows `gemini-4-hydrogen` (1.5/7.5), `gemini-4-argon` and `gemini-4-carbon` (2/10 — the promo rate, wrong after 2026-12-01 until the data updates), `gemini-4-neon` (3/15). It raises `LookupError` for `gemini-omni-1.2-flash`, and a plain token calc for image models returned text-output rates. Compute video and image cost ourselves (§1, §2). `pydantic_ai.prices.update_in_background()` refreshes prices hourly.

## 5. YouTube

(a) Upload + auth, following the official sample ([uploading_a_video](https://developers.google.com/youtube/v3/guides/uploading_a_video)); packages `google-api-python-client`, `google-auth-oauthlib`:

```python
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",        # videos.insert, thumbnails.set
    "https://www.googleapis.com/auth/youtube.readonly",      # videos.list on own videos; REQUIRED by reports.query
    "https://www.googleapis.com/auth/yt-analytics.readonly", # YouTube Analytics API
]
creds = Credentials.from_authorized_user_file("token.json", SCOPES) if os.path.exists("token.json") else None
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:  # Desktop-app client: opens browser, listens on http://localhost:<free port>
        creds = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
    open("token.json", "w").write(creds.to_json())

yt = build("youtube", "v3", credentials=creds)
req = yt.videos().insert(
    part="snippet,status",
    body={"snippet": {"title": t, "description": d, "tags": tags, "categoryId": "22"},
          "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                     "containsSyntheticMedia": True}},
    media_body=MediaFileUpload("short.mp4", chunksize=-1, resumable=True),
)
resp = None
while resp is None:
    _, resp = req.next_chunk()   # retry HTTP 500/502/503/504 and transport errors with backoff
video_id = resp["id"]
```

- `chunksize=-1` = one request, still resumable; use a multiple of 256 KB on flaky links. The sample sets `httplib2.RETRIES = 1` and does its own retries (max 10, sleep `random() * 2**n`).
- Omitted `privacyStatus` defaults to **public**. `status.publishAt` schedules a private video. `notifySubscribers` defaults to `True`.
- `reports.query`: "API requests to this method now require access to the `youtube.readonly` scope", in addition to an Analytics scope. Client: `build("youtubeAnalytics", "v2", credentials=creds)`. [reports.query](https://developers.google.com/youtube/analytics/reference/reports/query)

(b) Short classification: no API field marks an upload as a Short, and the API docs do not describe classification. Help Center: uploads **up to 3 minutes** with a **square or vertical** aspect ratio are Shorts (since 2024-10-15); max 1080p. Neither Help page mentions `#Shorts` as a requirement; whether it has any effect is UNCONFIRMED. Shorts over 1 minute with an active copyright claim are blocked globally. [three-minute Shorts](https://support.google.com/youtube/answer/15424877), [get started](https://support.google.com/youtube/answer/10059070)

(c) Thumbnails: yes. `yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload("thumb.png")).execute()`. For a Short call it **only after** `processingDetails.processingStatus == "succeeded"` (poll `videos.list(part="processingDetails")`), or it may not apply. JPEG/PNG, max 50 MB, ~50 units. New `shortsAspectRatio` (9:16) entry on the `thumbnails` resource. 403 `forbidden` if the channel lacks custom-thumbnail permission. [thumbnails.set](https://developers.google.com/youtube/v3/docs/thumbnails/set), [thumbnails](https://developers.google.com/youtube/v3/docs/thumbnails)

(d) Private lock: **no longer true.** 2026-11-02: "Videos uploaded through the videos.insert method from unverified API projects are no longer restricted to private viewing mode." Uploads may still default to private "based on creator account settings". [revision history](https://developers.google.com/youtube/v3/revision_history)

(e) OAuth "Testing": **still true.** External user type + "Testing" status → refresh token expires in **7 days**. Also max 100 refresh tokens per account per client; 6 months unused = invalid. Fix = publish to "In production"; verification consequences for YouTube scopes on a single-user local app are UNCONFIRMED. [oauth2](https://developers.google.com/identity/protocols/oauth2#expiration)

(f) Quota ([quota costs](https://developers.google.com/youtube/v3/determine_quota_cost)): `videos.insert` = 1 unit in the "Video Uploads" bucket, **100 calls/day**. `search.list` has its own 100/day bucket. All other methods share **10,000 units/day**: `videos.list` 1, `channels.list` 1, `videos.update` 50, `thumbnails.set` ~50. New `videos.batchGetStats`: 1 unit, own 10,000/day bucket. Reset at midnight Pacific.

(g) Stats:

- **Near-real-time (Data API)** `videos.list(part="statistics", id=...)`: `viewCount`, `likeCount`, `commentCount` only. No shares, retention or subscribers. Since 2026-08-27 `viewCount` counts the moment playback begins for all formats; since 2026-11-16 it includes TV co-views. [videos](https://developers.google.com/youtube/v3/docs/videos)
- **Analytics API** (`reports.query`, `ids="channel==MINE"`, `filters="video==ID"`): `views`, `engagedViews`, `averageViewDuration` (seconds), `averageViewPercentage`, `estimatedMinutesWatched`, `likes`, `comments`, `shares`, `subscribersGained`, `subscribersLost`; retention curve `audienceWatchRatio` by `elapsedVideoTimeRatio`. Shorts filter: `creatorContentType==SHORTS`. [metrics](https://developers.google.com/youtube/analytics/metrics), [channel reports](https://developers.google.com/youtube/analytics/channel_reports), [dimensions](https://developers.google.com/youtube/analytics/dimensions)
  - `engagedViews` = "viewed past the first frame, or the user clicks/taps to play"; excludes co-views. `subscribersGained` with a video filter counts only that video's watch page. `averageViewDuration` / `averageViewPercentage` exclude looping traffic.
- **Swipe-away / "Stayed to watch"**: a Studio metric ("percentage of times viewers stayed to watch past the initial seconds of a Short") that is **absent from the Analytics API metrics list**. `engagedViews / views` as a proxy is our own derivation — UNCONFIRMED. [Studio help](https://support.google.com/youtube/answer/12220281)
- **Freshness**: Analytics data has "a latency of 48 to 72 hours", `endDate` is truncated to the last fully processed day, granularity is daily. Google's own advice is `videos.list` for real-time counts. [data model](https://developers.google.com/youtube/analytics/data_model)

## 6. Analytics timing (when to snapshot)

- Official: Analytics API lags 48–72 h and is daily, so sub-day checkpoints can only use Data API view/like/comment counts. [data model](https://developers.google.com/youtube/analytics/data_model)
- Official: Studio's Realtime report compares 60-minute and 48-hour performance — the early windows YouTube itself surfaces. [overview help](https://support.google.com/youtube/answer/9314414)
- Official: the Shorts feed "may tune up on the recency of content"; what matters is "how viewers respond to each video when it's recommended to them". [recommendations help](https://support.google.com/youtube/answer/16559651)
- Official: "Publish time is not known to impact a video's long-term performance"; old videos taking off later is "common". [performance FAQ](https://support.google.com/youtube/answer/141805)
- YouTube staff via press (Todd Sherman, 2023): the system finds a "seed audience", then a Short "may get a lot more traffic or it may taper off"; delete-and-repost risks a spam signal. [TechCrunch](https://techcrunch.com/2023/08/25/youtube-demystifies-the-shorts-algorithm-views-and-answers-other-creator-questions/)
- Creator lore, no primary source found: curves like "most views land in 24–72 h" or "second wave at day 7–14". UNCONFIRMED — measure on our own channel.
- Suggested checkpoints (our inference): Data API at **1 h, 6 h, 24 h, 48 h**; first Analytics pull at **72 h**, then **7 d** and **28 d**; weekly `videos.batchGetStats` sweep to catch resurfacing.

## 7. UNCONFIRMED list (all flagged inline above)

(1) Our key's access to `gemini-omni-1.2-flash`, and whether `gemini-omni-flash-preview` (documented shut down, yet listed for our key) still works. (2) Omni via `generateContent`; Omni with `background=True`; Omni latency. (3) Billing basis of Omni extension turns and thinking tokens on Omni calls. (4) Live `gemini-nano-banana-2.1` call through Pydantic AI `ImageGenerator`. (5) Inline video limit (20 MB vs 100 MB) and video token rate (~100/s vs 263/s) — docs contradict themselves. (6) Any effect of `#Shorts`; classification of API uploads beyond the Help Center rule. (7) API equivalent of "Stayed to watch"; hour-level Shorts curves. (8) OAuth "In production" without verification for a single-user local app.
