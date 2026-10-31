"""Settings read from the environment (and .env). See PLAN.md §2.

Every seller-facing setting lives in app/memory.py, not here. This file only holds credentials,
addresses, limits and mode flags.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


class Settings:
    """Read once at import. LIVE-mode flags (OUTBOUND_ENABLED, DEMO_MODE) must be re-read from the
    environment at call time by the guard (PLAN.md §6.7), so those are exposed as properties."""

    CRUSTDATA_API_KEY: str = os.getenv("CRUSTDATA_API_KEY", "")
    CRUSTDATA_API_VERSION: str = os.getenv("CRUSTDATA_API_VERSION", "2025-11-01")
    COMPOSIO_API_KEY: str = os.getenv("COMPOSIO_API_KEY", "")
    COMPOSIO_USER_ID: str = os.getenv("COMPOSIO_USER_ID", "")
    SELLER_EMAIL: str = os.getenv("SELLER_EMAIL", "")
    SELLER_NAME: str = os.getenv("SELLER_NAME", "Kingslayers Demo")
    STAND_IN_EMAIL: str = os.getenv("STAND_IN_EMAIL", "")
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "agent_sdk")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "sonnet")
    BACKUP_ANTHROPIC_API_KEY: str = os.getenv("BACKUP_ANTHROPIC_API_KEY", "")
    BACKUP_ANTHROPIC_MODEL: str = os.getenv("BACKUP_ANTHROPIC_MODEL", "claude-sonnet-5-5")
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    DISCOVERY_COMPANY_LIMIT: int = int(os.getenv("DISCOVERY_COMPANY_LIMIT", "5"))
    CONTACTS_PER_COMPANY: int = int(os.getenv("CONTACTS_PER_COMPANY", "1"))
    CREDIT_CEILING_PER_RUN: float = float(os.getenv("CREDIT_CEILING_PER_RUN", "150"))
    ACCEPTED_EMAIL_STATUSES: list[str] = _list("ACCEPTED_EMAIL_STATUSES", "deliverable")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

    @property
    def DEMO_MODE(self) -> bool:
        return _bool("DEMO_MODE", "true")

    @property
    def OUTBOUND_ENABLED(self) -> bool:
        return _bool("OUTBOUND_ENABLED", "false")


S = Settings()
