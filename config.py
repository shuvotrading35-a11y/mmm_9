"""
Configuration — loaded from environment, validated with Pydantic v2.
All secrets are env-only, never hardcoded.
"""
import json
from decimal import Decimal
from typing import Annotated, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Bot ──────────────────────────────────────────────
    BOT_TOKEN: str
    BOT_USERNAME: str

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str  # postgresql+asyncpg://...

    # ── Redis ────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Admin ────────────────────────────────────────────
    ADMIN_IDS: Annotated[List[int], NoDecode] = Field(default_factory=list)
    SUPPORT_USERNAME: str = "@support"

    # ── Blockchain ───────────────────────────────────────
    BSC_RPC_URL: str = "https://bsc-dataseed.binance.org/"
    USDT_CONTRACT_ADDRESS: str = "0x55d398326f99059fF775485246999027B3197955"
    PAYOUT_WALLET_ADDRESS: str = ""
    PAYOUT_PRIVATE_KEY: str = ""  # NEVER log this

    # ── Financial Limits ─────────────────────────────────
    MIN_WITHDRAWAL: Decimal = Decimal("0.12")
    MAX_WITHDRAWAL: Decimal = Decimal("100.00")
    REFERRAL_REWARD: Decimal = Decimal("0.010")
    REFERRAL_COMMISSION_PCT: Decimal = Decimal("10")
    SPONSOR_MIN_DEPOSIT: Decimal = Decimal("1.00")
    TASK_MIN_REWARD: Decimal = Decimal("0.001")
    TASK_MAX_REWARD: Decimal = Decimal("1.000")
    MIN_DEPOSIT_CONFIRMATIONS: int = 12

    # ── Security ─────────────────────────────────────────
    SECRET_SALT: str = ""  # for idempotency key generation

    # ── Features ─────────────────────────────────────────
    AUTO_PAYOUT_ENABLED: bool = True
    MAINTENANCE_MODE: bool = False
    FORCE_JOIN_ENABLED: bool = True
    FRAUD_AUTO_BAN_SCORE: int = 76
    FRAUD_RESTRICT_SCORE: int = 51
    FRAUD_FLAG_SCORE: int = 26

    # ── Webhook ──────────────────────────────────────────
    WEBHOOK_URL: Optional[str] = None
    WEBHOOK_SECRET: Optional[str] = None
    WEBHOOK_PORT: int = 8443

    # ── Logging ──────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text

    # ── Rate Limits ──────────────────────────────────────
    RATE_TASK_VERIFY_LIMIT: int = 5
    RATE_TASK_VERIFY_WINDOW: int = 30
    RATE_WITHDRAW_LIMIT: int = 3
    RATE_WITHDRAW_WINDOW: int = 3600
    RATE_SUPPORT_LIMIT: int = 2
    RATE_SUPPORT_WINDOW: int = 3600
    RATE_START_LIMIT: int = 10
    RATE_START_WINDOW: int = 60

    # ── Validators ───────────────────────────────────────
    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if v is None or v == "":
            return []
        if isinstance(v, (list, tuple, set)):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            s = v.strip()
            # JSON ফরম্যাট: [1,2,3]
            if s.startswith("[") and s.endswith("]"):
                return [int(x) for x in json.loads(s)]
            # কমা দিয়ে আলাদা: 1,2,3
            return [int(x.strip()) for x in s.split(",") if x.strip()]
        return v

    @field_validator(
        "MIN_WITHDRAWAL", "MAX_WITHDRAWAL", "REFERRAL_REWARD",
        "SPONSOR_MIN_DEPOSIT", "TASK_MIN_REWARD", "TASK_MAX_REWARD",
        "REFERRAL_COMMISSION_PCT",
        mode="before",
    )
    @classmethod
    def parse_decimal(cls, v):
        return Decimal(str(v))

    @model_validator(mode="after")
    def validate_financial_limits(self):
        if self.MIN_WITHDRAWAL >= self.MAX_WITHDRAWAL:
            raise ValueError("MIN_WITHDRAWAL must be less than MAX_WITHDRAWAL")
        if self.TASK_MIN_REWARD >= self.TASK_MAX_REWARD:
            raise ValueError("TASK_MIN_REWARD must be less than TASK_MAX_REWARD")
        return self

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.ADMIN_IDS


settings = Settings()