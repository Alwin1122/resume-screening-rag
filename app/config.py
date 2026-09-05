from pathlib import Path

# Local only. Never commit a real key. Paste it here or set GROQ_API_KEY in the environment.
GROQ_API_KEY = ""

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
INCOMING_DIR = DATA_DIR / "incoming"
MAX_ZIP_FILES = 5000
MAX_ZIP_BYTES = 800 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
CHROMA_DIR = DATA_DIR / "chroma"
RESUMES_PATH = DATA_DIR / "resumes.json"
SHORTLIST_PATH = DATA_DIR / "shortlist.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
# Developer-tier IDs. llama-3.3-70b-versatile was retired 16 Aug 2026.
GROQ_MODELS = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
)

COLLECTION_NAME = "resumes"
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 220
RETRIEVE_CHUNKS = 24


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
