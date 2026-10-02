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

# Модели актуальны на октябрь 2026. Любую можно сменить переменной окружения.
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = _env("CLAUDE_EFFORT", "high")  # low | medium | high | xhigh | max
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-6.1-sol")
OPENAI_REASONING = _env("OPENAI_REASONING", "medium")  # low | medium | high | xhigh | max
OPENAI_IMAGE_MODEL = _env("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")  # быстрая
OPENAI_IMAGE_MODEL_HQ = _env("OPENAI_IMAGE_MODEL_HQ", "gpt-image-2.5-sunburst")  # максимальное качество
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_IMAGE_MODEL = _env("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")  # Nano Banana 2
GEMINI_IMAGE_MODEL_PRO = _env("GEMINI_IMAGE_MODEL_PRO", "gemini-3-pro-image")  # Nano Banana Pro
VEO_MODEL = _env("VEO_MODEL", "veo-3.1-generate-001")
VEO_FAST_MODEL = _env("VEO_FAST_MODEL", "veo-3.1-fast-generate-001")
OMNI_MODEL = _env("OMNI_MODEL", "gemini-omni-1.1-flash")  # генерация и редактирование видео
ELEVENLABS_TTS_MODEL = _env("ELEVENLABS_TTS_MODEL", "eleven_v4")
ELEVENLABS_TTS_FAST_MODEL = _env("ELEVENLABS_TTS_FAST_MODEL", "eleven_v4_turbo")
ELEVENLABS_STS_MODEL = _env("ELEVENLABS_STS_MODEL", "eleven_multilingual_sts_v2")
ELEVENLABS_DUBBING_MODEL = _env("ELEVENLABS_DUBBING_MODEL", "dubbing_v2")
ELEVENLABS_STT_MODEL = _env("ELEVENLABS_STT_MODEL", "scribe_v2")

MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "200"))


def available_providers() -> dict[str, bool]:
    return {
        "claude": bool(ANTHROPIC_API_KEY),
        "openai": bool(OPENAI_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
        "elevenlabs": bool(ELEVENLABS_API_KEY),
    }
