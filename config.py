
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App Settings
    APP_NAME: str = "Amazon Vendor Core"
    DEBUG: bool = False
    
    # DB Settings
    DATABASE_URL: str = "sqlite+aiosqlite:///./vendor_core.db"
    
    # Redis Settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # Security
    ENCRYPTION_KEY: str  # Generated via cryptography.fernet.Fernet.generate_key()
    
    # Paths
    CSV_OUTPUT_DIR: str = "./output/reports"
    
    # SP-API Defaults
    DEFAULT_REPORT_TYPE: str = "GET_VENDOR_REAL_TIME_SALES_REPORT"
    # DEFAULT_REPORT_TYPE: str = "GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA"
    SCHEDULER_INTERVAL_HOURS: int = 3

settings = Settings()
