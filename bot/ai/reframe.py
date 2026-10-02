"""Вертикальное кадрирование 16:9 → 9:16 с отслеживанием лица и нарезка клипов (ffmpeg + OpenCV YuNet)."""

import asyncio
import os
import tempfile
from pathlib import Path

from .llm import Media
from .media import _ffmpeg

MODEL = Path(__file__).resolve().parent.parent / "assets" / "face_detection_yunet_2023mar.onnx"
OUT_W, OUT_H = 1080, 1920
SAMPLE_STEP = 0.5  # как часто ищем лицо, секунд


def track_faces(path: str, start: float, end: float) -> tuple[int, int, list[tuple[float, float | None]]]:
    """Центр самого крупного лица по времени (секунды от start). None — лица в кадре нет."""
    import cv2

    cap = cv2.VideoCapture(path)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, 640 / max(w, 1))
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    detector = cv2.FaceDetectorYN.create(str(MODEL), "", (sw, sh), 0.6)
    points: list[tuple[float, float | None]] = []
    t = start
    while t <= end + 1e-6:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (sw, sh)) if scale < 1 else frame
        _, faces = detector.detect(small)
        cx = None
        if faces is not None and len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3] * f[-1])[:4]
            cx = float(x + fw / 2) / scale
        points.append((round(t - start, 3), cx))
        t += SAMPLE_STEP
    cap.release()
    return w, h, points


def crop_expression(points: list[tuple[float, float | None]], width: int, crop_w: int) -> str:
    """Плавная траектория кропа для ffmpeg: кусочно-линейная функция от времени t."""
    centers = [c for _, c in points]
    if not any(c is not None for c in centers):
        return str((width - crop_w) // 2)
    # заполняем пропуски ближайшим известным положением
    last = next(c for c in centers if c is not None)
    filled = []
    for c in centers:
        last = c if c is not None else last
        filled.append(last)
    # медиана по окну 5 убирает выбросы детектора; центрированное среднее с симметричным окном
    # убирает дрожание без задержки (линейное движение сохраняется точно, в том числе на краях)
    n = len(filled)
    med = []
    for i in range(n):
        k = min(2, i, n - 1 - i)
        window = sorted(filled[i - k: i + k + 1])
        med.append(window[len(window) // 2])
    smooth = []
    for i in range(n):
        k = min(3, i, n - 1 - i)
        window = med[i - k: i + k + 1]
        smooth.append(sum(window) / len(window))
    xs = [int(min(max(c - crop_w / 2, 0), width - crop_w)) // 2 * 2 for c in smooth]
    times = [t for t, _ in points]
    # оставляем только заметные изменения положения, чтобы выражение было коротким
    keys = [(times[0], xs[0])]
    for t, x in zip(times[1:], xs[1:]):
        if abs(x - keys[-1][1]) >= width * 0.015:
            keys.append((t, x))
    if keys[-1][0] != times[-1]:
        keys.append((times[-1], xs[-1]))
    if len(keys) == 1:
        return str(keys[0][1])
    expr = str(keys[-1][1])
    for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
        expr = f"if(lt(t,{t1:.2f}),{x0}+({x1 - x0})*(t-{t0:.2f})/{max(t1 - t0, 0.01):.2f},{expr})"
    return f"if(lt(t,{keys[0][0]:.2f}),{keys[0][1]},{expr})"


async def render_vertical(source: Media, start: float, end: float, ass: str | None = None,
                          track_face: bool = True, vertical: bool = True) -> bytes:
    """Вырезает отрезок, кадрирует в 9:16 по лицу (если исходник горизонтальный) и вшивает субтитры.
    vertical=False — оставляет исходные пропорции (только нарезка и субтитры)."""
    with tempfile.TemporaryDirectory() as tmp:
        src, subs, out = (os.path.join(tmp, n) for n in ("in", "subs.ass", "out.mp4"))
        with open(src, "wb") as f:
            f.write(source.data)
        import cv2

        cap = cv2.VideoCapture(src)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        crop_w = int(h * 9 / 16) // 2 * 2
        if not vertical:
            vf = "setsar=1"
        elif w > crop_w + 4:  # горизонтальный или квадратный — кадрируем
            if track_face:
                _, _, points = await asyncio.to_thread(track_faces, src, start, end)
                x = crop_expression(points, w, crop_w)
            else:
                x = str((w - crop_w) // 2)
            vf = f"crop={crop_w}:{h}:x='{x}':y=0,scale={OUT_W}:{OUT_H},setsar=1"
        else:  # уже вертикальный — приводим к 1080x1920 с полями при необходимости
            vf = (f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
                  f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2,setsar=1")
        if ass:
            with open(subs, "w", encoding="utf-8") as f:
                f.write(ass)
            vf += f",ass={subs}"
        await _ffmpeg(
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src, "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", out,
        )
        with open(out, "rb") as f:
            return f.read()


def output_size(source_w: int, source_h: int, vertical: bool) -> tuple[int, int]:
    """Размер кадра на выходе — под него рассчитываются субтитры."""
    return (OUT_W, OUT_H) if vertical else (source_w, source_h)
