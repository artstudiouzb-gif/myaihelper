"""Субтитры из пословной расшифровки: SRT и анимированные ASS (подсветка слов, «выпрыгивание»)."""

from dataclasses import dataclass

PUNCT_END = (".", "!", "?", "…", ",", ";", ":")


@dataclass
class Phrase:
    start: float
    end: float
    words: list[tuple[str, float, float]]

    @property
    def text(self) -> str:
        return " ".join(w for w, _, _ in self.words)


def phrases_from_words(words: list[dict], max_words: int = 4, max_gap: float = 0.6,
                       max_chars: int = 56) -> list[Phrase]:
    items = [w for w in words if w.get("type", "word") == "word" and w.get("start") is not None]
    phrases: list[Phrase] = []
    current: list[tuple[str, float, float]] = []
    for w in items:
        text, start, end = w["text"].strip(), float(w["start"]), float(w.get("end") or w["start"])
        if not text:
            continue
        too_long = sum(len(w) + 1 for w, _, _ in current) + len(text) > max_chars  # 2 строки по ~28 символов
        if current and (len(current) >= max_words or too_long or start - current[-1][2] > max_gap):
            phrases.append(Phrase(current[0][1], current[-1][2], current))
            current = []
        current.append((text, start, end))
        if text.endswith(PUNCT_END):
            phrases.append(Phrase(current[0][1], current[-1][2], current))
            current = []
    if current:
        phrases.append(Phrase(current[0][1], current[-1][2], current))
    return phrases


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def to_srt(phrases: list[Phrase]) -> str:
    return "\n".join(
        f"{i}\n{_srt_time(p.start)} --> {_srt_time(p.end)}\n{p.text}\n" for i, p in enumerate(phrases, 1)
    )


def timeline(phrases: list[Phrase]) -> str:
    return "\n".join(f"[{p.start:06.2f}–{p.end:06.2f}] {p.text}" for p in phrases)


# Цвета ASS: &HBBGGRR&
PRESETS = {
    "Kinetic typography": dict(font="Montserrat", size=0.072, base="&H00FFFFFF", hi="&H0000E5FF", outline="&H00000000",
                               border=5, shadow=2, upper=True, box=False, pop=True),
    "Минимализм": dict(font="Montserrat", size=0.05, base="&H00FFFFFF", hi="&H00FFFFFF", outline="&H64000000",
                       border=0, shadow=1, upper=False, box=False, pop=False),
    "Яркий поп": dict(font="Montserrat", size=0.068, base="&H00FFFFFF", hi="&H00B469FF", outline="&H00000000",
                      border=6, shadow=0, upper=True, box=False, pop=True),
    "Неон / техно": dict(font="Montserrat", size=0.062, base="&H00FFFFFF", hi="&H00FFFF00", outline="&H00FF6A00",
                         border=4, shadow=0, upper=True, box=False, pop=True),
    "Корпоративный": dict(font="Montserrat", size=0.052, base="&H00FFFFFF", hi="&H00FFC864", outline="&H00000000",
                          border=0, shadow=0, upper=False, box=True, pop=False),
    "Документальный": dict(font="Noto Serif", size=0.05, base="&H00FFFFFF", hi="&H00D7F0FF", outline="&H00000000",
                           border=2, shadow=1, upper=False, box=False, pop=False),
}


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def to_ass(phrases: list[Phrase], width: int, height: int, style: str) -> str:
    p = PRESETS.get(style, PRESETS["Kinetic typography"])
    size = int(min(width, height) * p["size"] * (1.25 if height > width else 1))
    vertical = height > width
    # безопасные зоны Reels/TikTok/Shorts: снизу ~16% и справа ~11% кадра закрывает интерфейс платформы
    margin_v = int(height * (0.2 if vertical else 0.1))
    margin_l = int(width * 0.08)
    margin_r = int(width * (0.13 if vertical else 0.08))
    border_style = 3 if p["box"] else 1
    back = "&H99000000" if p["box"] else "&H00000000"
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Cap,{p['font']},{size},{p['hi']},{p['base']},{p['outline']},{back},-1,0,0,0,100,100,0,0,"
        f"{border_style},{p['border']},{p['shadow']},2,{margin_l},{margin_r},{margin_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for ph in phrases:
        intro = r"{\fad(60,60)"
        if p["pop"]:
            intro += r"\fscx80\fscy80\t(0,120,\fscx108\fscy108)\t(120,220,\fscx100\fscy100)"
        intro += "}"
        parts, cursor = [], ph.start
        for word, start, end in ph.words:
            gap = max(0, int(round((start - cursor) * 100)))
            if gap:
                parts.append(rf"{{\k{gap}}}")
            dur = max(1, int(round((end - start) * 100)))
            text = word.upper() if p["upper"] else word
            parts.append(rf"{{\kf{dur}}}{_escape(text)} ")
            cursor = end
        end = ph.end + 0.15
        lines.append(f"Dialogue: 0,{_ass_time(ph.start)},{_ass_time(end)},Cap,,0,0,0,,{intro}{''.join(parts).rstrip()}")
    return header + "\n".join(lines) + "\n"
