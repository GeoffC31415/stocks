from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PORTFOLIO_",
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    project_root: Path = _PROJECT_ROOT
    deployment_mode: Literal["local", "public"] = "local"
    public_origin: str | None = None
    auth_username: SecretStr | None = None
    auth_password_hash: SecretStr | None = None
    frontend_dist: Path = _PROJECT_ROOT / "frontend" / "dist"
    max_request_body_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=10 * 1024 * 1024)
    database_url: str | None = None
    trading212_api_key: SecretStr | None = None
    trading212_api_secret: SecretStr | None = None
    trading212_account_name: str = "Trading 212"

    # Browser download automation (values live only in the git-ignored .env).
    hl_username: SecretStr | None = None
    hl_date_of_birth: SecretStr | None = None
    hl_password: SecretStr | None = None
    hl_secure_number: SecretStr | None = None
    barclays_surname: SecretStr | None = None
    barclays_membership_number: SecretStr | None = None
    barclays_pin: SecretStr | None = None
    barclays_passcode: SecretStr | None = None
    barclays_memorable_word: SecretStr | None = None
    sync_inbox: Path = Path("data/auto_downloaded")
    browser_profile: Path = Path("~/.local/share/stocks-browser")
    sync_stale_days: int = 7

    def resolved_sync_inbox(self) -> Path:
        path = self.sync_inbox.expanduser()
        return path if path.is_absolute() else (self.project_root / path).resolve()

    def resolved_browser_profile(self) -> Path:
        return self.browser_profile.expanduser().resolve()

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.project_root / "portfolio.db").resolve()
        return f"sqlite+aiosqlite:///{db_path}"


settings = Settings()
