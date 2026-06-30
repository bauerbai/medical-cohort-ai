from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str


@dataclass(frozen=True)
class LLMSettings:
    router_base_url: str | None
    router_api_key: str | None
    router_model: str | None
    request_timeout_seconds: float = 45.0

    @property
    def enabled(self) -> bool:
        return bool(self.router_base_url and self.router_api_key and self.router_model)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


settings = Settings(
    db_host=_required_env("DB_HOST"),
    db_port=int(_required_env("DB_PORT")),
    db_name=_required_env("DB_NAME"),
    db_user=_required_env("DB_USER"),
    db_password=_required_env("DB_PASSWORD"),
)

llm_settings = LLMSettings(
    router_base_url=os.getenv("LLM_ROUTER_BASE_URL"),
    router_api_key=os.getenv("LLM_ROUTER_API_KEY"),
    router_model=os.getenv("LLM_ROUTER_MODEL"),
    request_timeout_seconds=float(os.getenv("LLM_ROUTER_TIMEOUT_SECONDS", "45")),
)
