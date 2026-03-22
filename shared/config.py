from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Trading Monorepo"
    ENVIRONMENT: str = "development"

    # Redis configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    # MySQL configuration
    MYSQL_HOST: str = "mysql"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "rootpass"
    MYSQL_DATABASE: str = "vn30f1m_db"

    class Config:
        env_file = ".env"

settings = Settings()
