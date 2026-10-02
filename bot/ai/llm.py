"""Единый интерфейс к текстовым моделям: Claude, ChatGPT (OpenAI) и Gemini."""

import asyncio
import base64
import io
import logging
from dataclasses import dataclass

from .. import config

log = logging.getLogger(__name__)

PROVIDER_NAMES = {"claude": "Claude", "openai": "ChatGPT", "gemini": "Gemini", "elevenlabs": "ElevenLabs"}
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
# Файлы больше этого размера отправляются в Gemini через Files API, а не внутри запроса
GEMINI_INLINE_LIMIT = 15 * 1024 * 1024
MAX_TOKENS = 8000
# Gemini ждёт немного другие MIME-типы, чем отдают браузеры
GEMINI_MIME_FIX = {"video/quicktime": "video/mov", "audio/mpeg": "audio/mp3", "audio/x-wav": "audio/wav",
                   "audio/x-m4a": "audio/aac", "audio/mp4": "audio/aac"}


class AIError(Exception):
    """Ошибка, текст которой можно показать пользователю."""


@dataclass
class Media:
    data: bytes
    mime: str
    name: str = "file"

    @property
    def is_image(self) -> bool:
        return self.mime in IMAGE_MIMES

    @property
    def is_video(self) -> bool:
        return self.mime.startswith("video/")

    @property
    def is_audio(self) -> bool:
        return self.mime.startswith("audio/")


_clients: dict[str, object] = {}


def _claude():
    if "claude" not in _clients:
        from anthropic import AsyncAnthropic

        _clients["claude"] = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY, timeout=600)
    return _clients["claude"]


def openai_client():
    if "openai" not in _clients:
        from openai import AsyncOpenAI

        _clients["openai"] = AsyncOpenAI(api_key=config.OPENAI_API_KEY, timeout=600)
    return _clients["openai"]


def gemini_client():
    if "gemini" not in _clients:
        from google import genai

        _clients["gemini"] = genai.Client(api_key=config.GEMINI_API_KEY)
    return _clients["gemini"]


def require(provider: str) -> None:
    if not config.available_providers().get(provider):
        name = PROVIDER_NAMES.get(provider, provider)
        raise AIError(f"Не задан API-ключ для {name}. Добавьте его в настройки сервера (.env).")


async def generate_text(provider: str, system: str, prompt: str, media: list[Media] | None = None) -> str:
    media = media or []
    if provider != "gemini" and any(not m.is_image for m in media):
        # Видео и аудио понимает только Gemini — переключаемся на него автоматически
        if not config.GEMINI_API_KEY:
            raise AIError("Видео и аудио умеет анализировать только Gemini — добавьте GEMINI_API_KEY.")
        provider = "gemini"
    require(provider)
    if provider == "claude":
        return await _claude_text(system, prompt, media)
    if provider == "openai":
        return await _openai_text(system, prompt, media)
    if provider == "gemini":
        return await _gemini_text(system, prompt, media)
    raise AIError(f"Неизвестная модель: {provider}")


async def _claude_text(system: str, prompt: str, media: list[Media]) -> str:
    content: list[dict] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": m.mime, "data": base64.b64encode(m.data).decode()},
        }
        for m in media
    ]
    content.append({"type": "text", "text": prompt})
    resp = await _claude().messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


async def _openai_text(system: str, prompt: str, media: list[Media]) -> str:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for m in media:
        url = f"data:{m.mime};base64,{base64.b64encode(m.data).decode()}"
        content.append({"type": "image_url", "image_url": {"url": url}})
    resp = await openai_client().chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
    )
    return (resp.choices[0].message.content or "").strip()


async def gemini_parts(media: list[Media]) -> list:
    """Готовит файлы для Gemini: маленькие — прямо в запросе, большие — через Files API."""
    from google.genai import types

    client = gemini_client()
    parts = []
    for m in media:
        m = Media(m.data, GEMINI_MIME_FIX.get(m.mime, m.mime), m.name)
        if len(m.data) <= GEMINI_INLINE_LIMIT:
            parts.append(types.Part.from_bytes(data=m.data, mime_type=m.mime))
            continue
        uploaded = await client.aio.files.upload(
            file=io.BytesIO(m.data), config=types.UploadFileConfig(mime_type=m.mime)
        )
        for _ in range(120):  # видео обрабатывается на стороне Google, ждём до ~4 минут
            if uploaded.state and uploaded.state.name != "PROCESSING":
                break
            await asyncio.sleep(2)
            uploaded = await client.aio.files.get(name=uploaded.name)
        if not uploaded.state or uploaded.state.name != "ACTIVE":
            raise AIError("Gemini не смог обработать файл. Попробуйте файл поменьше.")
        parts.append(types.Part.from_uri(file_uri=uploaded.uri, mime_type=m.mime))
    return parts


async def _gemini_text(system: str, prompt: str, media: list[Media]) -> str:
    from google.genai import types

    contents = await gemini_parts(media) + [prompt]
    resp = await gemini_client().aio.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    text = (resp.text or "").strip()
    if not text:
        raise AIError("Gemini вернул пустой ответ (возможно, сработал фильтр безопасности).")
    return text
