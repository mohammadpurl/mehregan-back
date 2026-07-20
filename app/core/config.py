import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# بارگذاری .env قبل از خواندن SECRET_KEY و سایر تنظیمات
load_dotenv(BASE_DIR / ".env", override=False)

# Storage directories
PERSIST_DIRECTORY = Path(
    os.getenv("CHROMA_DB_DIR", BASE_DIR / "storage" / "chroma")
).as_posix()
UPLOAD_DIRECTORY = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "data" / "uploads"))
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

# Database
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{(BASE_DIR / 'storage' / 'app.db').as_posix()}"
)

# Embeddings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
HF_TIMEOUT = int(
    os.getenv("HF_TIMEOUT", "120")
)  # Timeout for Hugging Face downloads (seconds)

# LLM selection
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

# Retrieval defaults
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

# Reranker
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Auth — SECRET_KEY must be set via environment (no fallback in source)
_secret_raw = (os.getenv("SECRET_KEY") or "").strip()
_INSECURE_SECRET_DEFAULTS = frozenset(
    {
        "",
        "change-this-secret",
        "CHANGE_ME",
        "CHANGE_ME_BACKEND_JWT_SECRET",
        "CHANGE_ME_BACKEND_JWT_SECRET_64CHARS",
        "CHANGE_ME_USE_openssl_or_PowerShell_random_64_chars",
        # previously committed insecure fallback — never reuse
        "1ARYojrkXsRics0LHnOymE/U00KTfyhTLAgGYZo2paRZEDnxbUGK/X1DmT7X8ph1W/xbqE6OyhoFuvVd9hcSyn4N3QU=",
    }
)
if _secret_raw in _INSECURE_SECRET_DEFAULTS or len(_secret_raw) < 32:
    raise RuntimeError(
        "SECRET_KEY is missing or weak. Set a strong secret via environment "
        "(at least 32 characters; never use placeholder defaults)."
    )
SECRET_KEY = _secret_raw
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
# Swagger / ReDoc / OpenAPI JSON — off in production unless ENABLE_API_DOCS=true
_enable_docs_raw = os.getenv("ENABLE_API_DOCS", "").strip().lower()
if _enable_docs_raw in {"1", "true", "yes", "on"}:
    ENABLE_API_DOCS = True
elif _enable_docs_raw in {"0", "false", "no", "off"}:
    ENABLE_API_DOCS = False
else:
    ENABLE_API_DOCS = ENVIRONMENT not in {"production", "prod"}

# Reverse-proxy subpath (empty = local dev at http://localhost:8000/auth/...)
# Set ROOT_PATH=/backend in .env when API is served under /backend
_root_raw = os.getenv("ROOT_PATH")
if _root_raw is None:
    ROOT_PATH = "/backend"
else:
    ROOT_PATH = _root_raw.strip().rstrip("/")

# Swagger Authorize uses form login at /auth/token (not JSON /auth/login)
OAUTH2_TOKEN_URL = f"{ROOT_PATH}/auth/token" if ROOT_PATH else "/auth/token"

# Optional: full origin for avatar URLs in API (e.g. http://localhost:8000)
API_PUBLIC_BASE_URL = os.getenv("API_PUBLIC_BASE_URL", "").strip().rstrip("/")

# CORS
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000",
).split(",")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"

# Rate Limiting
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# فقط localhost/docker به‌صورت پیش‌فرض؛ IPهای عمومی را فقط از env اضافه کنید
DEFAULT_ALLOWED_IPS = [
    "127.0.0.1",
    "::1",
    "172.17.0.0/16",
    "172.18.0.0/16",
    "172.19.0.0/16",
]
ALLOWED_IPS: List[str] = [
    ip.strip()
    for ip in os.getenv("ALLOWED_IPS", ",".join(DEFAULT_ALLOWED_IPS)).split(",")
    if ip.strip()
]

IP_WHITELIST_ENABLED = os.getenv("IP_WHITELIST_ENABLED", "true").lower() == "true"
# فقط وقتی پشت reverse-proxy قابل اعتماد هستید true کنید
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
# Only LB health checks should bypass IP whitelist (never expose /docs publicly)
IP_WHITELIST_EXEMPT_PATHS = [
    "/health",
]
