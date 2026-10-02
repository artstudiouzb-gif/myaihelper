"""Видео: Veo 3.1 и Gemini Omni Flash 1.1 (Google, ключ Gemini).

Sora API OpenAI отключил 24.09.2026, поэтому видео делается только через Google.
"""

import asyncio
import base64
import io
import logging

from .. import config
from .llm import GEMINI_INLINE_LIMIT, GEMINI_MIME_FIX, AIError, Media, gemini_client, require

log = logging.getLogger(__name__)

POLL_SECONDS = 10
MAX_WAIT = 20 * 60


def _image(m: Media):
    from google.genai import types

    return types.Image(image_bytes=m.data, mime_type=m.mime)


async def veo(prompt: str, image: Media | None, refs: list[Media], aspect: str, seconds: int,
              resolution: str, fast: bool) -> bytes:
    """Veo 3.1: текст/кадр → видео со звуком. Референсы (до 3) — персонаж/предметы, только 8 секунд."""
    require("gemini")
    from google.genai import types

    client = gemini_client()
    seconds = 8 if refs and not image else min(max(seconds, 4), 8)
    if seconds not in (4, 6, 8):
        seconds = 8
    cfg = types.GenerateVideosConfig(
        aspect_ratio=aspect, duration_seconds=seconds, resolution=resolution, number_of_videos=1,
    )
    if refs and not image:
        cfg.reference_images = [
            types.VideoGenerationReferenceImage(image=_image(m), reference_type="asset") for m in refs[:3]
        ]
    op = await client.aio.models.generate_videos(
        model=config.VEO_FAST_MODEL if fast else config.VEO_MODEL,
        prompt=prompt, image=_image(image) if image else None, config=cfg,
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


async def _omni_media(m: Media) -> dict:
    """Контент для Omni: маленькие файлы — внутри запроса, большие видео — через Files API."""
    mime = GEMINI_MIME_FIX.get(m.mime, m.mime)
    kind = "video" if m.is_video else "image"
    if len(m.data) <= GEMINI_INLINE_LIMIT:
        return {"type": kind, "data": base64.b64encode(m.data).decode(), "mime_type": mime}
    from google.genai import types

    client = gemini_client()
    uploaded = await client.aio.files.upload(file=io.BytesIO(m.data), config=types.UploadFileConfig(mime_type=mime))
    for _ in range(120):
        if uploaded.state and uploaded.state.name != "PROCESSING":
            break
        await asyncio.sleep(2)
        uploaded = await client.aio.files.get(name=uploaded.name)
    return {"type": kind, "uri": uploaded.uri, "mime_type": mime}


async def omni(prompt: str, task: str, media: list[Media], aspect: str, resolution: str) -> bytes:
    """Gemini Omni Flash 1.1. task: text_to_video | image_to_video | reference_to_video | edit | extend."""
    require("gemini")
    client = gemini_client()
    content = [await _omni_media(m) for m in media]
    content.append({"type": "text", "text": prompt})
    response_format = {"type": "video", "resolution": resolution}
    if task != "edit":  # при редактировании пропорции берутся из исходного видео
        response_format["aspect_ratio"] = aspect
    interaction = await client.aio.interactions.create(
        model=config.OMNI_MODEL,
        input=content,
        response_format=response_format,
        generation_config={"video_config": {"task": task}},
        background=True,
    )
    waited = 0
    while interaction.status in ("queued", "in_progress"):
        if waited >= MAX_WAIT:
            raise AIError("Gemini Omni генерирует слишком долго. Попробуйте позже.")
        await asyncio.sleep(POLL_SECONDS)
        waited += POLL_SECONDS
        interaction = await client.aio.interactions.get(interaction.id)
    if interaction.status != "completed":
        error = getattr(interaction, "error", None)
        raise AIError(f"Gemini Omni: {getattr(error, 'message', None) or interaction.status}")
    out = interaction.output_video
    if out and out.data:
        return base64.b64decode(out.data)
    if out and out.uri:
        data = await client.aio.files.download(file=out.uri)
        if data:
            return data
    raise AIError("Gemini Omni не вернул видео — вероятно, сработал фильтр безопасности.")


async def generate_video(engine: str, prompt: str, image: Media | None = None, refs: list[Media] | None = None,
                         aspect: str = "9:16", seconds: int = 8, resolution: str = "1080p") -> bytes:
    refs = refs or []
    if engine == "omni":
        if image:
            return await omni(prompt, "image_to_video", [image], aspect, resolution)
        if refs:
            return await omni(prompt, "reference_to_video", refs[:3], aspect, resolution)
        return await omni(prompt, "text_to_video", [], aspect, resolution)
    return await veo(prompt, image, refs, aspect, seconds, resolution, fast=engine == "veo_fast")


async def edit_video(source: Media, instruction: str, refs: list[Media], task: str = "edit",
                     resolution: str = "1080p", aspect: str = "9:16") -> bytes:
    """Редактирование (замена персонажа, фона, стиля) или продление существующего видео через Omni."""
    return await omni(instruction, task, [source, *refs[:3]], aspect, resolution)
