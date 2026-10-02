"""Генерация изображений: GPT Image 2.5 (OpenAI) и Nano Banana 2 / Pro (Google)."""

import base64

from .. import config
from .llm import AIError, Media, gemini_client, openai_client, require

# Движок → (провайдер, модель)
ENGINES = {
    "flare": ("openai", lambda: config.OPENAI_IMAGE_MODEL),
    "sunburst": ("openai", lambda: config.OPENAI_IMAGE_MODEL_HQ),
    "nb2": ("gemini", lambda: config.GEMINI_IMAGE_MODEL),
    "nbpro": ("gemini", lambda: config.GEMINI_IMAGE_MODEL_PRO),
}
ALIASES = {"openai": "flare", "gemini": "nb2"}

# Размер → (пропорции, разрешение) для Gemini
SIZES = {
    "1024x1024": ("1:1", "1K"), "1024x1536": ("2:3", "1K"), "1536x1024": ("3:2", "1K"),
    "1152x2048": ("9:16", "2K"), "2048x1152": ("16:9", "2K"), "2048x2048": ("1:1", "2K"),
    "2160x3840": ("9:16", "4K"), "3840x2160": ("16:9", "4K"),
}


def provider_of(engine: str) -> str:
    return ENGINES[ALIASES.get(engine, engine)][0]


async def openai_image(model: str, prompt: str, refs: list[Media], size: str, quality: str) -> list[bytes]:
    require("openai")
    client = openai_client()
    kwargs = {"model": model, "prompt": prompt, "size": size, "quality": quality}
    if refs:
        resp = await client.images.edit(image=[(f"ref{i}.png", m.data, m.mime) for i, m in enumerate(refs)], **kwargs)
    else:
        resp = await client.images.generate(**kwargs)
    images = [base64.b64decode(d.b64_json) for d in (resp.data or []) if d.b64_json]
    if not images:
        raise AIError("OpenAI не вернул изображение.")
    return images


async def gemini_image(model: str, prompt: str, refs: list[Media], size: str) -> list[bytes]:
    require("gemini")
    from google.genai import types

    contents: list = [types.Part.from_bytes(data=m.data, mime_type=m.mime) for m in refs]
    contents.append(prompt)
    cfg = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
    if size in SIZES:
        aspect, resolution = SIZES[size]
        cfg.image_config = types.ImageConfig(aspect_ratio=aspect, image_size=resolution)
    resp = await gemini_client().aio.models.generate_content(model=model, contents=contents, config=cfg)
    images = []
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else None) or []:
            if part.inline_data and part.inline_data.data:
                images.append(part.inline_data.data)
    if not images:
        raise AIError("Gemini не вернул изображение (возможно, сработал фильтр безопасности).")
    return images


async def generate_image(engine: str, prompt: str, refs: list[Media] | None = None,
                         size: str = "1024x1024", quality: str = "auto") -> list[bytes]:
    engine = ALIASES.get(engine, engine)
    provider, model = ENGINES.get(engine, ENGINES["nb2"])
    if provider == "gemini":
        return await gemini_image(model(), prompt, refs or [], size)
    return await openai_image(model(), prompt, refs or [], size, quality)
