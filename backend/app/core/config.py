from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    demo_auth_enabled: bool = False
    ai_provider: str = "mock"
    database_url: str = "postgresql+psycopg_async://cloudagent:cloudagent@localhost:5432/cloudagent"
    max_active_runs: int = 4
    max_sessions: int = 100
    max_runs: int = 1000


settings = Settings()

if settings.demo_auth_enabled and settings.app_env != "local":
    raise RuntimeError("Demo auth may only be enabled in APP_ENV=local")
if settings.ai_provider != "mock":
    raise RuntimeError("Stage A supports AI_PROVIDER=mock only")
