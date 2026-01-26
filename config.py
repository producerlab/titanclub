from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-1003442983833"))

# Admin IDs (для команд администратора)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Database (поддержка PostgreSQL для Railway)
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway автоматически добавляет для PostgreSQL
if DATABASE_URL:
    # Railway использует postgres://, но SQLAlchemy нужен postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    DB_URL = DATABASE_URL
else:
    DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///database.db")

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Rate Limiting
DAILY_REQUEST_LIMIT = int(os.getenv("DAILY_REQUEST_LIMIT", "100"))
RATE_LIMIT_WARNING_THRESHOLD = int(os.getenv("RATE_LIMIT_WARNING_THRESHOLD", "80"))

# File limits
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(10 * 1024 * 1024)))  # 10 MB по умолчанию

# OpenAI timeouts
OPENAI_RUN_TIMEOUT = int(os.getenv("OPENAI_RUN_TIMEOUT", "120"))  # секунды
