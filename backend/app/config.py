import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "cashiq.db").replace("\\", "/")
ENV_FILE_PATH = os.path.join(BASE_DIR, ".env")

class Settings(BaseSettings):
    PROJECT_NAME: str = "CashIQ API"
    API_V1_STR: str = "/api"
    SECRET_KEY: str = "supersecretkey_please_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DB_PATH}"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"]
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    AI_PROVIDER: str = "openai"  # "openai" or "gemini"
    AI_MODEL: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_ignore_empty=True, extra="ignore")

settings = Settings()

def save_env_variables(vars_dict: dict):
    """Persists key-value pairs into backend/.env and updates live settings."""
    lines = []
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    existing_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in vars_dict:
                new_lines.append(f"{k}={vars_dict[k]}\n")
                existing_keys.add(k)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for k, v in vars_dict.items():
        if k not in existing_keys:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Update runtime settings and environment
    for k, v in vars_dict.items():
        os.environ[k] = str(v)
        if hasattr(settings, k):
            setattr(settings, k, v)

