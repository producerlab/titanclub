import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-1003442983833"))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Database
DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///database.db")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Rate Limiting
DAILY_REQUEST_LIMIT = int(os.getenv("DAILY_REQUEST_LIMIT", "100"))
RATE_LIMIT_WARNING_THRESHOLD = int(os.getenv("RATE_LIMIT_WARNING_THRESHOLD", "80"))
