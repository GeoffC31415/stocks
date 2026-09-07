from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PORTFOLIO_",
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = _PROJECT_ROOT
    database_url: str | None = None
    trading212_api_key: SecretStr | None = None
    trading212_api_secret: SecretStr | None = None
    trading212_account_name: str = "Trading 212"

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.project_root / "portfolio.db").resolve()
        return f"sqlite+aiosqlite:///{db_path}"


settings = Settings()
