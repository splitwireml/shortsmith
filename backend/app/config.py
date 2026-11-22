"""Paths and secrets, read from the repo-root `.env` at runtime.

Nothing here runs at import time beyond defining the class, so importing
this module never opens `.env`. The Gemini key is a SecretStr so it cannot
leak through a repr or a log line; code that needs it (S2) calls
`config.gemini_api_key.get_secret_value()`.
"""

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        populate_by_name=True,  # allow the gemini_api_key= kwarg next to the env aliases
        extra="ignore",
    )

    # Different Google tools use different names for the same key; accept both
    # so nobody has to open .env to find out which one is in there.
    gemini_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    data_dir: Path = REPO_ROOT / "data"
    # Tests turn the background worker loop off and drive every step
    # themselves; start-up recovery still runs either way.
    run_worker: bool = True
    # The built SvelteKit app FastAPI serves (S5); a missing folder
    # just means API only. Tests point this at a temp folder.
    frontend_dir: Path = REPO_ROOT / "frontend" / "build"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def youtube_token_path(self) -> Path:
        return self.data_dir / "youtube_token.json"
