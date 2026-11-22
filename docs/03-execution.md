# Execution plan — for the manager

You are the manager. You do not write product code. You run five sprints by starting fresh
worker agents with `hc`, keep them unblocked, run the tests once per sprint, and commit.
The owner is away and has asked not to be consulted: decide, note the decision, move on.
Goal: working app, fast, clean. Not a production hardening exercise.

## Workers

| Role | Template | Job |
|---|---|---|
| Tester | `opus-xhigh` | Writes the sprint's tests from the spec, before the code exists. |
| Coder | `wonder-full-max` | Makes the tests pass. Writes all product code. |
| Reviewer | `sol62-xhigh` (`sol62-max` for S2 and the final review) | Reads the diff for needless complexity. |

New tester, coder and reviewer for every sprint; kill and remove the old ones
(`hc kill <t>; hc rm <t>`) once the sprint is committed. Never reuse a worker across sprints.

### `hc` notes (learned the hard way)
- Run `hc --skill` once for the manual. Always `hc run --bg --name <role>-s<n> --cwd <repo> <template> "<task>"`.
- Check `first_message.sent` in the launch output. If false: `hc read <t>`, fix, then send.
- **Codex workers open on a "Hooks need review" dialog.** Choose *Continue without
  trusting*: `hc keys <t> down down enter`, confirm with `hc read <t> --lines 0` that the
  prompt is showing, then `hc send <t> "<task>"` (the launch task is lost to the dialog).
  Do not choose "Trust all" — that is the owner's decision, and the workers run fine without it.
- A worker may open on a "do you trust this folder?" dialog for this repo. Accept it (this is
  the owner's own project), then send the task. Any other permission or trust prompt: decline
  or pick the option that grants nothing.
- Wait with `hc wait --children any`, never sleep or poll.
- Workers must not start agents of their own.

## The loop (same for every sprint)

1. **Brief.** Each worker's first message is short: its role, the sprint section below, and
   "read `AGENTS.md`, `docs/02-architecture.md`, `docs/research.md`". Do not paste the spec
   into the message and do not forward other agents' chatter. Workers get context from files.
2. **Tests first.** Tester writes tests for the sprint's "Tests" list against the interfaces
   in the architecture doc. Few, behavioural, through public functions and HTTP routes —
   no test-per-function suites. Tester confirms they fail for the right reason, reports, done.
3. **Code.** Coder implements until `uv run pytest -q` is green. If a test contradicts the
   spec, the coder fixes the test and lists it in the report.
4. **Review.** Reviewer reads `git diff` for the sprint and reports at most 12 findings,
   ranked, each with file:line and a concrete simpler alternative. Looking for: unneeded
   abstractions, duplication, files doing two jobs, unclear names, dead code, spec drift,
   anything a newcomer could not follow. Not looking for: exotic edge cases, theoretical
   security issues in a localhost app, style nits a formatter would catch. Reviewer does not
   run the tests and does not edit code.
5. **Fix.** Send the findings to the same coder. One round. The coder may decline a finding
   with a one-line reason.
6. **Close.** You run the tests once, commit (`S<n>: <what>`, local only, never push), kill
   the three workers.

No CI, no per-task builds, no second review round. If a sprint is stuck after two coder
attempts at the same failure, start a fresh `opus-max` to diagnose that one failure only.

## Sprints

Order: **S1 → S2 → (S3 and S4 at the same time) → S5.** S3 only touches `backend/`, S4 only
touches `frontend/` and `backend/app/help_articles.json`, so they cannot collide.

### S1 — Foundation: data, storage, money, recipes
Scope: `backend/pyproject.toml`, `app/{main,config,db,models,storage,costs,presets}.py`,
`app/api/{pipelines,settings,costs,status}.py`.
Tests: storage put/get/list/delete and rejection of keys that escape the data folder ·
cost recording and the summary maths (by stage, by pipeline, by day, per video, per view,
projection) · budget check blocks when over · pipeline CRUD and presets · settings round-trip
and no secret ever appears in any response · status endpoint reports each check.

### S2 — The engine: plan, generate, review, approve
Scope: `app/agents/{base,planner,reviewer}.py`, `app/{media,stitch,pipeline}.py`,
`app/api/{videos,media}.py`.
Tests: a queued video reaches `awaiting_approval` in practice mode with a fake text model ·
every paid step leaves a cost event with the right stage · planner prompt contains only the
brief, ≤10 lessons, ≤15 past titles (V2) · reviewer flags clip 2 → only clip 2 is regenerated,
once (V3) · failure then Retry does not regenerate finished clips (V4) · over budget → failed,
nothing spent (C3) · approve / reject / feedback routes, notes become lessons (A2–A4) ·
auto-approve above the score.

### S3 — YouTube, learning, scheduling, clean-up
Scope: `app/{youtube,scheduler,retention}.py`, `app/agents/{analyst,helper}.py`,
`app/api/{youtube,insights,help}.py`. Fold `scripts/youtube_connect.py` into `app/youtube.py`
and delete the script; keep the token path and scopes identical.
Tests (Google fully mocked): publish stores the YouTube id and a second call does not upload
again (Y2) · a video found in `publishing` at start-up becomes `failed` with the "check your
channel" message · snapshots are taken exactly at the due checkpoints · analyst runs at most
once a day per pipeline and never leaves more than 10 active lessons (L2) · due videos are
created from `every_days` / `videos_per_run` · clean-up by age and by size (S2) · expired
Google token → `needs_reconnect` (Y3) · help "ask" answers are grounded in the articles and
cost is recorded under `help`.

### S4 — The web app
Scope: all of `frontend/`, `backend/app/help_articles.json` (the real help content),
`start.command`. The coder should use the Svelte skills / current Svelte 5 docs if its
harness has them. The user is non-technical: this sprint is where the product is won or lost.
Tests (vitest, pure logic only): help search ranking · money and time formatting · the API
client turns server errors into plain-language messages.
Review for this sprint additionally includes opening the app in practice mode and walking
through: setup guide → create recipe from a preset → make a practice video → approve →
costs page → help search. Report anything confusing to a non-technical person.

### S5 — Join up, prove it, real run
Scope: FastAPI serves the built frontend · `start.command` works from a clean checkout ·
`README.md` (one page: how to start it, then a short developer section) · practice-mode
end-to-end test through the HTTP API · final whole-repo review by `sol62-max` for
complexity, one clean-up pass · then the real run below.

## Real money rules

Total Gemini spend for this whole build: **hard stop at $10** (owner's ceiling is $10–15).
The app's own cost ledger is the meter — every real call goes through the app code, never
through an ad-hoc script, so it is recorded. Check the ledger total before each real call.

Allowed real calls, in this order, each only after the mocked tests for that code are green:
1. One planner call (cents) — proves Pydantic AI + Hydrogen + structured output.
2. One thumbnail image (cents).
3. One video clip of 3 s at 720p (about $0.21) — proves the Omni call shape and measures latency.
4. One review call on that clip.
5. **The end-to-end run: exactly one real Short**, two clips of 10 s at 720p (about $1.40,
   up to about $2.10 if the reviewer has one clip redone), through every stage, approved by you on the owner's behalf (the
   owner pre-authorised exactly one unattended upload), uploaded as **private**.
   Then one statistics snapshot to prove the analytics read path.

Rules for step 5: use the estimates in `docs/research.md` to confirm the run fits the
remaining budget before starting; if it does not, drop to one clip. Exactly one upload —
if the upload errors after bytes were sent, list the channel's uploads before any retry.
If `data/youtube_token.json` does not exist (the owner has not yet clicked Allow in the
browser tab opened by `yt-oauth`), finish everything else, leave the real run as one
documented command, and say so in the final report. Do not automate the Google consent
screen.

If a real call fails because the API differs from `docs/research.md`, fix the code and the
research doc, and count the failed attempts against the budget. Three failed paid attempts
at the same step → stop that step and report.

## Finish

Write `docs/REPORT.md` (one page): what works, what was verified with real APIs and what
only in practice mode, total real spend by stage from the ledger, the YouTube video id of the
real upload, decisions you made that the owner might not expect, what is left. Then
`hc send t5d "<5-line summary + path to the report>"`. Message `t5d` earlier only if
something makes the whole build impossible.
