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


async def fit_image(image: Media, width: int, height: int) -> Media:
    """Обрезает и масштабирует картинку точно под размер кадра (нужно для Sora)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "fit.jpg")
        with open(src, "wb") as f:
            f.write(image.data)
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        await _ffmpeg("-i", src, "-vf", vf, "-q:v", "2", dst)
        with open(dst, "rb") as f:
            return Media(f.read(), "image/jpeg", "frame.jpg")
