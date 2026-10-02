"""ffmpeg: извлечение звука и кадров, замена звуковой дорожки."""

import asyncio
import os
import tempfile

from .llm import AIError, Media


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


async def extract_frame(video: Media, at: float = 0.3) -> Media:
    """Берёт кадр из видео (по умолчанию почти первый) в JPEG."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "frame.jpg")
        with open(src, "wb") as f:
            f.write(video.data)
        await _ffmpeg("-ss", str(at), "-i", src, "-frames:v", "1", "-q:v", "2", dst)
        with open(dst, "rb") as f:
            return Media(f.read(), "image/jpeg", "frame.jpg")


async def probe_size(video: Media) -> tuple[int, int]:
    """Ширина и высота видео (с учётом поворота с телефона)."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in")
        with open(src, "wb") as f:
            f.write(video.data)
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:stream_side_data=rotation", "-of", "json", src,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
    import json

    try:
        stream = json.loads(out)["streams"][0]
        w, h = int(stream["width"]), int(stream["height"])
        rotation = next((abs(int(d.get("rotation", 0))) for d in stream.get("side_data_list", [])), 0)
        return (h, w) if rotation in (90, 270) else (w, h)
    except (KeyError, IndexError, ValueError):
        return 1080, 1920


async def to_mp3(audio: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "out.mp3")
        with open(src, "wb") as f:
            f.write(audio)
        await _ffmpeg("-i", src, "-b:a", "192k", dst)
        with open(dst, "rb") as f:
            return f.read()


async def burn_subtitles(video: Media, ass: str) -> bytes:
    """Вшивает субтитры ASS (с анимацией) в видео."""
    with tempfile.TemporaryDirectory() as tmp:
        src, subs, out = (os.path.join(tmp, n) for n in ("in", "subs.ass", "out.mp4"))
        with open(src, "wb") as f:
            f.write(video.data)
        with open(subs, "w", encoding="utf-8") as f:
            f.write(ass)
        await _ffmpeg(
            "-i", src, "-vf", f"ass={subs}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out,
        )
        with open(out, "rb") as f:
            return f.read()
