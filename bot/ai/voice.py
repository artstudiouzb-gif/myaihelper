"""ElevenLabs: озвучка (Eleven v4), клон, замена голоса, дубляж (Dubbing v2) и расшифровка (Scribe v2)."""

import asyncio

import aiohttp

from .. import config
from .llm import AIError, Media, require
from .media import to_audio

API = "https://api.elevenlabs.io/v1"
TIMEOUT = aiohttp.ClientTimeout(total=600)


def _headers() -> dict:
    require("elevenlabs")
    return {"xi-api-key": config.ELEVENLABS_API_KEY}


async def _check(resp: aiohttp.ClientResponse) -> None:
    if resp.status >= 400:
        body = await resp.text()
        raise AIError(f"ElevenLabs: ошибка {resp.status}. {body[:300]}")


async def list_voices() -> list[dict]:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.get(f"{API}/voices", headers=_headers()) as r:
            await _check(r)
            data = await r.json()
    voices = [
        {"id": v["voice_id"], "name": v.get("name", ""), "category": v.get("category", "")}
        for v in data.get("voices", [])
    ]
    # Свои (клонированные) голоса — первыми
    voices.sort(key=lambda v: (v["category"] not in ("cloned", "generated", "professional"), v["name"].lower()))
    return voices


async def text_to_speech(voice_id: str, text: str, fast: bool = False) -> bytes:
    """Eleven v4 понимает теги эмоций прямо в тексте: [laughs], [whispers], [excited] и т.п."""
    url = f"{API}/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    body = {
        "text": text,
        "model_id": config.ELEVENLABS_TTS_FAST_MODEL if fast else config.ELEVENLABS_TTS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(url, headers=_headers(), json=body) as r:
            await _check(r)
            return await r.read()


async def clone_voice(name: str, samples: list[Media], remove_noise: bool) -> str:
    form = aiohttp.FormData()
    form.add_field("name", name)
    form.add_field("remove_background_noise", "true" if remove_noise else "false")
    for i, m in enumerate(samples):
        audio = await to_audio(m)
        form.add_field("files", audio.data, filename=f"sample{i}.mp3", content_type=audio.mime)
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(f"{API}/voices/add", headers=_headers(), data=form) as r:
            await _check(r)
            return (await r.json())["voice_id"]


async def speech_to_speech(voice_id: str, audio: Media, remove_noise: bool) -> bytes:
    form = aiohttp.FormData()
    form.add_field("audio", audio.data, filename="input.mp3", content_type=audio.mime)
    form.add_field("model_id", config.ELEVENLABS_STS_MODEL)
    form.add_field("remove_background_noise", "true" if remove_noise else "false")
    url = f"{API}/speech-to-speech/{voice_id}?output_format=mp3_44100_128"
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(url, headers=_headers(), data=form) as r:
            await _check(r)
            return await r.read()


# --- Дубляж (Dubbing v2): перевод голосами самих спикеров, фон и музыка сохраняются ---

DUB_POLL_SECONDS = 10
DUB_MAX_WAIT = 40 * 60


async def dub(media: Media, target_lang: str) -> bytes:
    """Возвращает дублированную дорожку (FLAC без потерь) — её вставляют обратно в видео."""
    form = aiohttp.FormData()
    ext = "mp4" if media.is_video else "mp3"
    form.add_field("file", media.data, filename=f"source.{ext}", content_type=media.mime)
    form.add_field("model_id", config.ELEVENLABS_DUBBING_MODEL)
    form.add_field("reference", "myaihelper")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(f"{API}/dubbing/project", headers=_headers(), data=form) as r:
            await _check(r)
            project_id = (await r.json())["project_id"]
        # Язык можно добавить сразу: задача начнётся, когда исходник будет расшифрован
        async with s.post(f"{API}/dubbing/project/{project_id}/language", headers=_headers(),
                          json={"target_language": target_lang}) as r:
            await _check(r)
            language_id = (await r.json())["language_id"]

        waited = 0
        while True:
            await asyncio.sleep(DUB_POLL_SECONDS)
            waited += DUB_POLL_SECONDS
            async with s.get(f"{API}/dubbing/project/{project_id}/language/{language_id}", headers=_headers()) as r:
                await _check(r)
                info = await r.json()
            status = info.get("status")
            if status == "completed":
                url = (info.get("outputs") or {}).get("lossless_audio")
                if not url:
                    raise AIError("ElevenLabs: дубляж готов, но ссылка на файл не пришла.")
                break
            if status in ("failed", "cancelled"):
                raise AIError(f"ElevenLabs: дубляж не удался. {info.get('error') or info.get('warnings') or ''}".strip())
            if waited % 60 == 0:  # проверяем, не упал ли сам проект (например, не удалось расшифровать)
                async with s.get(f"{API}/dubbing/project/{project_id}", headers=_headers()) as r:
                    if r.status < 400 and (await r.json()).get("status") == "failed":
                        raise AIError("ElevenLabs: не удалось обработать исходный файл.")
            if waited >= DUB_MAX_WAIT:
                raise AIError("ElevenLabs: дубляж идёт слишком долго. Попробуйте ролик короче.")

        async with s.get(url) as r:  # подписанная ссылка, ключ не нужен
            await _check(r)
            return await r.read()


# --- Расшифровка речи (Scribe v2): текст с точными таймкодами каждого слова ---


async def transcribe(media: Media, language: str = "") -> dict:
    """Возвращает {"language_code", "text", "words": [{"text", "start", "end", "type", "speaker_id"}]}."""
    audio = await to_audio(media)
    form = aiohttp.FormData()
    form.add_field("file", audio.data, filename="audio.mp3", content_type=audio.mime)
    form.add_field("model_id", config.ELEVENLABS_STT_MODEL)
    form.add_field("timestamps_granularity", "word")
    form.add_field("diarize", "true")
    form.add_field("tag_audio_events", "false")
    if language:
        form.add_field("language_code", language)
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(f"{API}/speech-to-text", headers=_headers(), data=form) as r:
            await _check(r)
            return await r.json()


# --- Музыка (Eleven Music) и звуковые эффекты ---


async def compose_music(prompt: str, seconds: float, instrumental: bool = True) -> bytes:
    body = {
        "prompt": prompt,
        "music_length_ms": int(min(max(seconds, 3), 600) * 1000),
        "model_id": config.ELEVENLABS_MUSIC_MODEL,
        "force_instrumental": instrumental,
    }
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(f"{API}/music?output_format=auto", headers=_headers(), json=body) as r:
            await _check(r)
            return await r.read()


async def sound_effect(text: str, seconds: float | None = None, loop: bool = False) -> bytes:
    body = {"text": text, "model_id": config.ELEVENLABS_SFX_MODEL, "prompt_influence": 0.5, "loop": loop}
    if seconds:
        body["duration_seconds"] = min(max(seconds, 0.5), 30)
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(f"{API}/sound-generation?output_format=mp3_44100_128", headers=_headers(), json=body) as r:
            await _check(r)
            return await r.read()
