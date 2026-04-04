from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_", extra="ignore")

    project_root: Path = Path(__file__).resolve().parents[2]
    database_url: str | None = None

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = (self.project_root / "portfolio.db").resolve()
        return f"sqlite+aiosqlite:///{db_path}"


settings = Settings()
