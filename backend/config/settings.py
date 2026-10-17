"""
Django settings for the NL-to-Regex processing platform.

Configuration is driven entirely by environment variables (12-factor) so the
same image runs unchanged in docker-compose and in a deployed environment.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core ---------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-secret-key")
DEBUG = _env_bool("DJANGO_DEBUG", "1")
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "*") or ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "apps.jobs",
    "apps.s3connector",
    "apps.processing",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

# --- Database (Postgres for concurrent job persistence) -----------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "regexdb"),
        "USER": os.environ.get("POSTGRES_USER", "regex"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "regexpass"),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Allow tests / lightweight runs to fall back to SQLite.
if _env_bool("USE_SQLITE", "0"):
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- I18N / TZ ----------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static -------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- DRF ----------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
}

# --- CORS ---------------------------------------------------------------
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8080"
)
CORS_ALLOW_HEADERS = ["content-type", "accept", "origin", "authorization"]

# --- Redis / cache ------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# --- Celery -------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_DEFAULT_QUEUE = "processing"
# Keep results around long enough for polling.
CELERY_RESULT_EXPIRES = 60 * 60 * 24

# --- LLM ----------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5")
LLM_CACHE_TTL_SECONDS = int(os.environ.get("LLM_CACHE_TTL_SECONDS", "86400"))

# --- Spark --------------------------------------------------------------
SPARK_MASTER = os.environ.get("SPARK_MASTER", "local[*]")
SPARK_DRIVER_MEMORY = os.environ.get("SPARK_DRIVER_MEMORY", "2g")
SPARK_EXECUTOR_MEMORY = os.environ.get("SPARK_EXECUTOR_MEMORY", "2g")
SPARK_ROWS_PER_PARTITION = int(os.environ.get("SPARK_ROWS_PER_PARTITION", "200000"))

# --- Results storage ----------------------------------------------------
RESULTS_DIR = os.environ.get("RESULTS_DIR", "/data/results")

# --- Credential encryption ---------------------------------------------
# Fernet key used to encrypt user AWS credentials before they ever touch
# Redis / Postgres. If unset, derive a stable key from SECRET_KEY (dev only).
CREDENTIALS_ENCRYPTION_KEY = os.environ.get("CREDENTIALS_ENCRYPTION_KEY", "")

# --- Logging: never log credentials; keep it simple + structured --------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
