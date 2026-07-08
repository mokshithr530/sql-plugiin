import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

# ============================
# Gemini Configuration
# ============================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

GEMINI_API_KEYS = [
    key.strip()
    for key in os.getenv("GEMINI_API_KEYS", GEMINI_API_KEY).split(",")
    if key.strip()
]

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ============================
# Database Configuration
# ============================

UPLOAD_FOLDER = "uploads"

TEMP_DATABASE_FOLDER = "temp_databases"

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
