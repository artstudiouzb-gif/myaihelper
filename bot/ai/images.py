"""Генерация изображений: OpenAI (GPT Image) и Gemini (Nano Banana)."""

import base64

from .. import config
from .llm import AIError, Media, gemini_client, openai_client, require


async def openai_image(prompt: str, refs: list[Media] | None = None, size: str = "1024x1024") -> list[bytes]:
    require("openai")
    client = openai_client()
    if refs:
        resp = await client.images.edit(
            model=config.OPENAI_IMAGE_MODEL,
            image=[(f"ref{i}.png", m.data, m.mime) for i, m in enumerate(refs)],
            prompt=prompt,
            size=size,
        )
    else:
        resp = await client.images.generate(model=config.OPENAI_IMAGE_MODEL, prompt=prompt, size=size)
    images = [base64.b64decode(d.b64_json) for d in (resp.data or []) if d.b64_json]
    if not images:
        raise AIError("OpenAI не вернул изображение.")
    return images


async def gemini_image(prompt: str, refs: list[Media] | None = None, aspect: str | None = None) -> list[bytes]:
    require("gemini")
    from google.genai import types

    contents: list = [types.Part.from_bytes(data=m.data, mime_type=m.mime) for m in refs or []]
    contents.append(prompt)
    cfg = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
    if aspect:
        cfg.image_config = types.ImageConfig(aspect_ratio=aspect)
    resp = await gemini_client().aio.models.generate_content(
        model=config.GEMINI_IMAGE_MODEL, contents=contents, config=cfg
    )
    images = []
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else None) or []:
            if part.inline_data and part.inline_data.data:
                images.append(part.inline_data.data)
    if not images:
        raise AIError("Gemini не вернул изображение (возможно, сработал фильтр безопасности).")
    return images


# Соответствие размеров OpenAI и пропорций Gemini
SIZE_TO_ASPECT = {"1024x1024": "1:1", "1024x1536": "2:3", "1536x1024": "3:2"}


async def generate_image(engine: str, prompt: str, refs: list[Media] | None = None, size: str = "1024x1024") -> list[bytes]:
    if engine == "gemini":
        return await gemini_image(prompt, refs, SIZE_TO_ASPECT.get(size))
    return await openai_image(prompt, refs, size)
