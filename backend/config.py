import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent

if load_dotenv:
    load_dotenv(BASE_DIR / ".env")

# ============================
# LLM Configuration
# ============================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("GEMINI_API_KEY", ""))

LLM_API_KEYS = [
    key.strip()
    for key in os.getenv("LLM_API_KEYS", LLM_API_KEY).split(",")
    if key.strip()
]

LLM_MODEL = os.getenv(
    "LLM_MODEL",
    os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
)

LLM_FALLBACK_MODELS = [
    model.strip()
    for model in os.getenv(
        "LLM_FALLBACK_MODELS",
        "gemini-2.5-flash-lite,gemini-2.0-flash",
    ).split(",")
    if model.strip()
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", LLM_API_KEY)

GEMINI_API_KEYS = [
    key.strip()
    for key in os.getenv(
        "GEMINI_API_KEYS",
        os.getenv("LLM_API_KEYS", GEMINI_API_KEY),
    ).split(",")
    if key.strip()
]

GEMINI_MODEL = os.getenv("GEMINI_MODEL", LLM_MODEL)

GEMINI_FALLBACK_MODELS = [
    model.strip()
    for model in os.getenv(
        "GEMINI_FALLBACK_MODELS",
        ",".join(LLM_FALLBACK_MODELS),
    ).split(",")
    if model.strip()
]

GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))

# ============================
# Database Configuration
# ============================

UPLOAD_FOLDER = str(BASE_DIR / "uploads")

TEMP_DATABASE_FOLDER = str(BASE_DIR / "temp_databases")

SUPPORTED_DATABASES = [
    ".db",
    ".sqlite",
    ".sql"
]

SUPPORTED_DATABASE_NOTES = {
    ".db": "SQLite database file",
    ".sqlite": "SQLite database file",
    ".sql": "SQL dump imported into SQLite"
}

QUERY_ROW_LIMIT = int(os.getenv("QUERY_ROW_LIMIT", "100"))

# ============================
# Session Configuration
# ============================

MAX_CHAT_HISTORY = 20

MAX_RETRIES = 2

# ============================
# SQL Configuration
# ============================

BLOCKED_SQL_KEYWORDS = [

    "DROP",

    "DELETE",

    "UPDATE",

    "INSERT",

    "ALTER",

    "CREATE",

    "TRUNCATE",

    "ATTACH",

    "DETACH",

    "REPLACE",

    "PRAGMA"

]
