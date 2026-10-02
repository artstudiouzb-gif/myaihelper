"""Настройки бота. Всё читается из переменных окружения (или файла .env)."""

import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _ids(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


def _public_url() -> str:
    """Публичный HTTPS-адрес Mini App. На Railway/Render определяется сам."""
    url = _env("WEBAPP_URL")
    if not url and _env("RAILWAY_PUBLIC_DOMAIN"):
        url = "https://" + _env("RAILWAY_PUBLIC_DOMAIN")
    if not url:
        url = _env("RENDER_EXTERNAL_URL")
    return url.rstrip("/")


BOT_TOKEN = _env("BOT_TOKEN")
ALLOWED_USER_IDS = _ids(_env("ALLOWED_USER_IDS"))
WEBAPP_URL = _public_url()
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8080"))
# Только для локальной проверки интерфейса в обычном браузере. На сервере не включать!
DEV_SKIP_AUTH = _env("DEV_SKIP_AUTH") == "1"

ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _env("OPENAI_API_KEY")
GEMINI_API_KEY = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")

CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-5-5")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-5.5")
OPENAI_IMAGE_MODEL = _env("OPENAI_IMAGE_MODEL", "gpt-image-2")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_IMAGE_MODEL = _env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
ELEVENLABS_TTS_MODEL = _env("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")
ELEVENLABS_STS_MODEL = _env("ELEVENLABS_STS_MODEL", "eleven_multilingual_sts_v2")

MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "200"))


def available_providers() -> dict[str, bool]:
    return {
        "claude": bool(ANTHROPIC_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "elevenlabs": bool(ELEVENLABS_API_KEY),
    }
