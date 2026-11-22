# Shortsmith — rules for every agent working in this repo

A local YouTube Shorts automation app. Python backend (FastAPI + Pydantic AI + SQLite),
SvelteKit frontend. Read `docs/02-architecture.md` before writing code. Read
`docs/research.md` before touching any Google / Gemini / Pydantic AI / YouTube call —
these APIs are newer than your training data; do not write them from memory.

## Secrets — non-negotiable
- Never open, print, log, copy or commit `.env`, `credentials.json` or anything in `data/`.
  Code loads them at runtime; you never need to see the values.
- Never put a secret in a test, a fixture, a doc, a commit message or a message to
  another agent. Never send them to any service other than Google's own APIs.
- The API never returns secrets to the browser. The server binds to `127.0.0.1` only.

## Money — non-negotiable
- Tests never make a paid call. Everything external is mocked (see architecture, "Testing").
- No real Gemini or YouTube call unless the manager explicitly tells you to make that one call.

## Code style
- Simple, boring, readable by a human who has never seen the project. Small files
  (aim under 250 lines), small functions, clear names, type hints.
- No abstraction without two real users of it: no base classes, factories, registries,
  plugin systems, or config for values that never change.
- No new dependency for something a few lines of standard library can do.
- Comments say why, not what. No docstring essays.
- Follow the module boundaries in the architecture doc. If the doc is wrong, say so in your
  report instead of working around it.

## Working here
- Backend: `cd backend && uv run pytest -q`. Frontend: `cd frontend && pnpm check && pnpm build`.
- Stay inside the files your task names. Do not start other agents unless told to.
- Do not commit; the manager commits.
- When done or stuck, report to whoever assigned the task with `hc send <their id> "<result>"`:
  what you changed, what you skipped, anything you were unsure about. Keep it under 15 lines.
