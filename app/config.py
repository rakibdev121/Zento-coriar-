"""Application settings, read from environment variables (or a local .env file)."""
from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 720
    cors_origins: str = ""
    currency: str = "BDT"  # shown as the taka sign in the apps
    wallet_min_deposit: Decimal = Decimal("50")
    wallet_min_withdraw: Decimal = Decimal("100")
    # Where customers send money for a deposit (shown on the wallet page). Leave empty to hide a method.
    pay_bkash: str = ""
    pay_nagad: str = ""
    pay_rocket: str = ""
    pay_bank: str = ""
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Admin"
    rider_commission_rate: Decimal = Decimal("0.20")  # share of the parcel price a rider earns on delivery
    rider_daily_goal: Decimal = Decimal("2000")  # daily earnings goal shown in the rider app

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, v: str) -> str:
        v = v.strip()
        # Supabase / Heroku-style URLs use postgres:// or postgresql://; use the psycopg 3 driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @field_validator("secret_key")
    @classmethod
    def _check_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return v

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
