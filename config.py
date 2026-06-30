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
