"""Генерация видео: Veo (Google, ключ Gemini) и Sora (OpenAI)."""

import asyncio
import logging
import re

from .. import config
from .llm import AIError, Media, gemini_client, openai_client, require
from .media import fit_image

log = logging.getLogger(__name__)

POLL_SECONDS = 10
MAX_WAIT = 20 * 60
VEO_FALLBACK = "veo-3.1-fast-generate-preview"
_veo_model: str | None = None


async def veo_model() -> str:
    """Модель из VEO_MODEL или самая свежая доступная (предпочтительно fast — она дешевле)."""
    global _veo_model
    if config.VEO_MODEL:
        return config.VEO_MODEL
    if _veo_model:
        return _veo_model
    try:
        names = []
        async for m in await gemini_client().aio.models.list():
            name = (m.name or "").split("/")[-1]
            if name.startswith("veo-"):
                names.append(name)

        def version(n: str) -> float:
            found = re.search(r"veo-(\d+(?:\.\d+)?)", n)
            return float(found.group(1)) if found else 0.0

        pool = [n for n in names if "fast" in n] or names
        pool.sort(key=lambda n: (version(n), "preview" not in n), reverse=True)
        _veo_model = pool[0] if pool else VEO_FALLBACK
    except Exception as e:  # список моделей недоступен — берём известную
        log.warning("cannot list Veo models: %s", e)
        _veo_model = VEO_FALLBACK
    log.info("Veo model: %s", _veo_model)
    return _veo_model


async def veo(prompt: str, image: Media | None, refs: list[Media], aspect: str, seconds: int) -> bytes:
    require("gemini")
    from google.genai import types

    client = gemini_client()
    cfg = types.GenerateVideosConfig(aspect_ratio=aspect, duration_seconds=min(seconds, 8), number_of_videos=1)
    if refs and not image:
        cfg.reference_images = [
            types.VideoGenerationReferenceImage(
                image=types.Image(image_bytes=m.data, mime_type=m.mime), reference_type="asset"
            )
            for m in refs[:3]
        ]
    op = await client.aio.models.generate_videos(
        model=await veo_model(),
        prompt=prompt,
        image=types.Image(image_bytes=image.data, mime_type=image.mime) if image else None,
        config=cfg,
    )
    waited = 0
    while not op.done:
        if waited >= MAX_WAIT:
            raise AIError("Veo генерирует слишком долго. Попробуйте позже.")
        await asyncio.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        op = await client.aio.operations.get(op)
    if op.error:
        raise AIError(f"Veo: {op.error.get('message', op.error) if isinstance(op.error, dict) else op.error}")
    resp = op.response or op.result
    videos = (resp.generated_videos if resp else None) or []
    if not videos:
        reasons = ", ".join((resp.rai_media_filtered_reasons or []) if resp else [])
        raise AIError("Veo не вернул видео — вероятно, сработал фильтр безопасности. " + reasons)
    video = videos[0].video
    if video.video_bytes:
        return video.video_bytes
    data = await client.aio.files.download(file=video)
    if not data:
        raise AIError("Не удалось скачать видео из Veo.")
    return data


SORA_SIZES = {"9:16": (720, 1280), "16:9": (1280, 720)}


async def sora(prompt: str, image: Media | None, aspect: str, seconds: int) -> bytes:
    require("openai")
    client = openai_client()
    w, h = SORA_SIZES.get(aspect, SORA_SIZES["9:16"])
    secs = "12" if seconds >= 12 else "8" if seconds >= 6 else "4"
    kwargs = {}
    if image:
        frame = await fit_image(image, w, h)
        kwargs["input_reference"] = ("frame.jpg", frame.data, "image/jpeg")
    job = await client.videos.create(model=config.SORA_MODEL, prompt=prompt, seconds=secs, size=f"{w}x{h}", **kwargs)
    waited = 0
    while job.status in ("queued", "in_progress"):
        if waited >= MAX_WAIT:
            raise AIError("Sora генерирует слишком долго. Попробуйте позже.")
        await asyncio.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        job = await client.videos.retrieve(job.id)
    if job.status != "completed":
        message = getattr(job.error, "message", None) or "видео не создано"
        raise AIError(f"Sora: {message}")
    content = await client.videos.download_content(job.id)
    return content.content


async def generate_video(engine: str, prompt: str, image: Media | None = None, refs: list[Media] | None = None,
                         aspect: str = "9:16", seconds: int = 8) -> bytes:
    if engine == "sora":
        return await sora(prompt, image or (refs[0] if refs else None), aspect, seconds)
    return await veo(prompt, image, refs or [], aspect, seconds)
