"""ElevenLabs: озвучка текста, клонирование голоса и замена голоса (speech-to-speech)."""

import asyncio
import os
import tempfile

import aiohttp

from .. import config
from .llm import AIError, Media, require

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


# --- ffmpeg: извлечь звук из видео и вставить новый звук обратно ---


async def _ffmpeg(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-loglevel", "error", *args,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise AIError(f"ffmpeg: {err.decode(errors='ignore')[:300]}")


async def to_audio(m: Media) -> Media:
    """Видео → mp3. Аудио возвращается как есть."""
    if not m.is_video:
        return m
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "out.mp3")
        with open(src, "wb") as f:
            f.write(m.data)
        await _ffmpeg("-i", src, "-vn", "-ac", "1", "-ar", "44100", "-b:a", "128k", dst)
        with open(dst, "rb") as f:
            return Media(f.read(), "audio/mpeg", "audio.mp3")


async def replace_audio(video: Media, audio_mp3: bytes) -> bytes:
    """Подменяет звуковую дорожку видео."""
    with tempfile.TemporaryDirectory() as tmp:
        v, a, out = (os.path.join(tmp, n) for n in ("in", "voice.mp3", "out.mp4"))
        with open(v, "wb") as f:
            f.write(video.data)
        with open(a, "wb") as f:
            f.write(audio_mp3)
        common = ["-i", v, "-i", a, "-map", "0:v:0", "-map", "1:a:0"]
        tail = ["-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
        try:
            await _ffmpeg(*common, "-c:v", "copy", *tail)
        except AIError:
            # Видеокодек не помещается в mp4 (например, webm) — перекодируем
            await _ffmpeg(*common, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", *tail)
        with open(out, "rb") as f:
            return f.read()
