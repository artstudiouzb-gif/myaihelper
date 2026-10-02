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


async def probe_duration(video: Media) -> float:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in")
        with open(src, "wb") as f:
            f.write(video.data)
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", src,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


async def qa_video(data: bytes, expect_audio: bool = True, expected_seconds: float | None = None) -> list[str]:
    """Проверка готового видео перед отправкой: поток, длительность, звук, чёрные кадры, тишина."""
    import json
    import re

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.mp4")
        with open(src, "wb") as f:
            f.write(data)
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", src,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        try:
            info = json.loads(out or b"{}")
            kinds = {s.get("codec_type") for s in info.get("streams", [])}
            duration = float(info.get("format", {}).get("duration", 0))
        except ValueError:
            return ["файл видео повреждён или не читается"]
        issues = []
        if "video" not in kinds:
            return ["в файле нет видеодорожки"]
        if duration < 0.5:
            return ["видео пустое (длительность меньше полсекунды)"]
        if expected_seconds and abs(duration - expected_seconds) > max(1.5, expected_seconds * 0.25):
            issues.append(f"длительность {duration:.1f} с вместо ожидаемых {expected_seconds:.0f} с")
        if expect_audio and "audio" not in kinds:
            issues.append("нет звуковой дорожки")
        # чёрные кадры и тишина (первые 10 минут — чтобы проверка длинных видео не занимала вечность)
        args = ["-hide_banner", "-t", "600", "-i", src, "-vf", "blackdetect=d=0.4:pic_th=0.98"]
        if "audio" in kinds:
            args += ["-af", "silencedetect=noise=-50dB:d=0.8"]
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", *args, "-f", "null", "-", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
    log = err.decode(errors="ignore")
    span = min(duration, 600)
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)]
    black_total = sum(b - a for a, b in blacks)
    if black_total > span * 0.3:
        issues.append(f"много чёрных кадров ({black_total:.1f} с из {span:.0f} с)")
    elif blacks and blacks[0][0] < 0.1 and blacks[0][1] > 1.0:
        issues.append(f"видео начинается с чёрного экрана ({blacks[0][1]:.1f} с)")
    silence = sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)", log))
    if expect_audio and "audio" in kinds and silence > span * 0.85:
        issues.append("звуковая дорожка почти пустая (тишина)")
    return issues


MUSIC_LEVELS = {"low": 0.12, "mid": 0.22, "high": 0.4}


async def mix_music(video: Media, music: bytes, level: str = "mid") -> bytes:
    """Подкладывает музыку под видео: зацикливает до длины ролика и приглушает её, когда звучит голос."""
    volume = MUSIC_LEVELS.get(level, MUSIC_LEVELS["mid"])
    with tempfile.TemporaryDirectory() as tmp:
        v, m, out = (os.path.join(tmp, n) for n in ("in", "music", "out.mp4"))
        with open(v, "wb") as f:
            f.write(video.data)
        with open(m, "wb") as f:
            f.write(music)
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", v,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        has_voice = bool((await proc.communicate())[0].strip())
        if has_voice:
            # sidechain: музыка проседает, пока говорит человек, и возвращается в паузах
            graph = (f"[1:a]volume={volume},aformat=channel_layouts=stereo[m];"
                     "[0:a]aformat=channel_layouts=stereo,asplit=2[voice][key];"
                     "[m][key]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[duck];"
                     "[voice][duck]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            graph = f"[1:a]volume={min(volume * 3, 1)},aformat=channel_layouts=stereo[a]"
        await _ffmpeg(
            "-i", v, "-stream_loop", "-1", "-i", m, "-filter_complex", graph, "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out,
        )
        with open(out, "rb") as f:
            return f.read()
