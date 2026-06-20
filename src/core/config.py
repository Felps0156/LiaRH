import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.0-flash")

SUPABASE_DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE")
EVOLUTION_WEBHOOK_TOKEN = os.getenv("EVOLUTION_WEBHOOK_TOKEN")

AGENT_MAX_HISTORY_MESSAGES = int(os.getenv("AGENT_MAX_HISTORY_MESSAGES", "12"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
