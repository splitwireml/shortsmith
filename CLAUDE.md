@AGENTS.md

## Test → dev → review loop (owner's setup)
Fixes and features go through three `hc` workers, in this order:
- Test writer: Claude Opus 5.5, xhigh — `hc` template `opus-xhigh`.
- Developer: Muse Code wonder-full, max — `hc` template `wonder-full-max`.
- Reviewer: Codex Sol 6.2, xhigh — `hc` template `sol62-xhigh`.
