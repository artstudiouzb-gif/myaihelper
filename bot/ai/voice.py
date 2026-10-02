"""ElevenLabs: озвучка текста, клонирование голоса и замена голоса (speech-to-speech)."""

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


async def text_to_speech(voice_id: str, text: str) -> bytes:
    url = f"{API}/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(url, headers=_headers(), json={"text": text, "model_id": config.ELEVENLABS_TTS_MODEL}) as r:
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


# --- Дубляж: перевод видео/аудио на другой язык голосами исходных спикеров с сохранением фона ---

DUB_POLL_SECONDS = 10
DUB_MAX_WAIT = 30 * 60


async def dub(media: Media, target_lang: str, source_lang: str = "auto", num_speakers: int = 0) -> tuple[bytes, str]:
    """Возвращает (файл, mime). Для видео ElevenLabs отдаёт mp4, для аудио — mp3."""
    form = aiohttp.FormData()
    ext = "mp4" if media.is_video else "mp3"
    form.add_field("file", media.data, filename=f"source.{ext}", content_type=media.mime)
    form.add_field("target_lang", target_lang)
    form.add_field("source_lang", source_lang)
    form.add_field("num_speakers", str(num_speakers))
    form.add_field("watermark", "false")
    form.add_field("drop_background_audio", "false")
    form.add_field("name", f"myaihelper-{target_lang}")
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        async with s.post(f"{API}/dubbing", headers=_headers(), data=form) as r:
            await _check(r)
            dubbing_id = (await r.json())["dubbing_id"]

        waited = 0
        while True:
            await asyncio.sleep(DUB_POLL_SECONDS)
            waited += DUB_POLL_SECONDS
            async with s.get(f"{API}/dubbing/{dubbing_id}", headers=_headers()) as r:
                await _check(r)
                info = await r.json()
            status = info.get("status")
            if status == "dubbed":
                break
            if status == "failed":
                raise AIError(f"ElevenLabs: дубляж не удался. {info.get('error', '')}".strip())
            if waited >= DUB_MAX_WAIT:
                raise AIError("ElevenLabs: дубляж идёт слишком долго. Попробуйте ролик короче.")

        async with s.get(f"{API}/dubbing/{dubbing_id}/audio/{target_lang}", headers=_headers()) as r:
            await _check(r)
            data = await r.read()
            mime = r.headers.get("Content-Type", "video/mp4" if media.is_video else "audio/mpeg").split(";")[0]
    return data, mime
