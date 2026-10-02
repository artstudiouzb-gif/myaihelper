"""Требования генераторов к промптам (по официальным гайдам, октябрь 2026) и их автоматическая проверка.

Правила подставляются в инструкцию модели, а готовые промпты проверяются кодом:
если формат нарушен, бот просит модель исправить ответ.
"""

import re
from dataclasses import dataclass

LIPSYNC_SEEDANCE = "EN, ZH, JA, KO, ES, FR, DE, PT"


@dataclass
class Generator:
    id: str
    name: str
    max_seconds: int
    rules: str  # инструкция модели; {seconds} подставляется


GENERATORS: dict[str, Generator] = {
    "veo": Generator(
        "veo", "Veo 3.1", 8,
        "ФОРМАТ ПРОМПТА VEO 3.1 (официальный гайд Google):\n"
        "- Формула: [Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance] — связным текстом на английском.\n"
        "- Ролик {seconds} с (Veo делает максимум 8 с). Несколько планов внутри ролика — таймкодами "
        "«[00:00-00:02] …», непрерывно от 00:00 до 00:0{seconds}, без выхода за {seconds} с.\n"
        "- Звук — отдельными предложениями: реплика в кавычках `A woman says, \"…\"` (короткая, на один вдох), "
        "«SFX: …» для конкретных звуков, «Ambient noise: …» для фона.\n"
        "- Исключения описывай утвердительно («an empty street with no cars»), а не списком «no …».\n"
        "- Если есть стартовый кадр — описывай только движение, действие и звук, не пересказывай картинку.\n"
        "- Длина промпта — до ~1024 токенов (обычно 60–200 слов).",
    ),
    "seedance": Generator(
        "seedance", "Seedance 2.5", 30,
        "ФОРМАТ ПРОМПТА SEEDANCE 2.5 (официальная структура из 4 частей, на английском):\n"
        "1) Asset binding — если есть референсы: «@Image1 = …» — у каждого одна роль (лицо и одежда героя, "
        "продукт, локация). Референс задаёт только эту роль, а не позу, свет и ракурс.\n"
        "2) Summary — одно предложение: кто, где, что происходит, жанр/стиль, основное движение камеры.\n"
        "3) Timeline — непрерывные отрезки в целых секундах от 0 до {seconds}, без пропусков: «0–3s: …», "
        "«3–7s: …». В каждом отрезке одно главное событие и ОДНО движение камеры. Реплики — в кавычках с "
        "указанием, кто говорит. Звук — конкретные шумы (footsteps, glass clink), а не «cinematic sound». "
        "Запреты пиши внутри отрезка: «no subtitles», «no BGM».\n"
        "4) Consistency — одна фраза о том, что неизменно весь ролик (свет, камера, внешность).\n"
        f"- Синхронизация губ работает для языков {LIPSYNC_SEEDANCE}. Если реплики на русском/узбекском — "
        "предупреди, что губы могут не совпасть, и предложи переозвучить через «Голоса → Дубляж».",
    ),
    "kling": Generator(
        "kling", "Kling 3.0", 15,
        "ФОРМАТ ПРОМПТА KLING 3.0 (на английском):\n"
        "- Порядок: Scene → Characters → Action → Camera → Audio & Style.\n"
        "- Несколько шагов действия допустимы, но с ясной последовательностью; длительность {seconds} с.\n"
        "- Негатив — встроенно в конце одной фразой (например: «avoid blurry hands, extra fingers, text, watermark»).",
    ),
    "grok": Generator(
        "grok", "Grok Imagine", 15,
        "ФОРМАТ ПРОМПТА GROK IMAGINE (на английском):\n"
        "- Формула: [Subject] + [Action] + [Environment] + [Style] + [Camera & lighting].\n"
        "- Для оживления картинки — короткий промпт движения (1–2 предложения), без повторного описания кадра.\n"
        "- Ролик до {seconds} с (максимум 15). Звук — конкретный («cloth rustle and footsteps», "
        "«product click and low bass»), а не «cinematic sound».",
    ),
    "omni": Generator(
        "omni", "Gemini Omni Flash 1.1", 10,
        "ФОРМАТ ПРОМПТА GEMINI OMNI (на английском):\n"
        "- Естественное описание: кто, что делает, где, камера, свет, стиль, звук; реплики в кавычках.\n"
        "- Ролик около {seconds} с (до 10 с за один проход).",
    ),
}

TARGET_OPTIONS = [(g.id, g.name) for g in (GENERATORS[k] for k in ("veo", "seedance", "kling", "grok"))]


def clamp_seconds(generator: str, seconds: int) -> int:
    gen = GENERATORS.get(generator, GENERATORS["veo"])
    return max(4, min(seconds, gen.max_seconds))


def rules_for(generator: str, seconds: int) -> str:
    gen = GENERATORS.get(generator, GENERATORS["veo"])
    return gen.rules.replace("{seconds}", str(clamp_seconds(generator, seconds)))


# ---------- проверка готовых промптов ----------

CODE_BLOCK = re.compile(r"```([^\n]*)\n(.*?)```", re.S)
SEEDANCE_SEGMENT = re.compile(r"(?<![\d:])(\d{1,3})\s*(?:–|-|—|to)\s*(\d{1,3})\s*s(?:ec(?:onds?)?)?\b", re.I)
VEO_STAMP = re.compile(r"\[(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\]")


def prompt_blocks(text: str) -> list[str]:
    """Промпты для генератора: блоки ```prompt. Если модель их не пометила — все блоки, кроме SRT/JSON/text."""
    blocks = [(lang.strip().lower(), body.strip()) for lang, body in CODE_BLOCK.findall(text)]
    tagged = [body for lang, body in blocks if lang == "prompt"]
    if tagged:
        return tagged
    return [body for lang, body in blocks if lang not in ("srt", "json", "text") and len(body.split()) >= 12]


def _segments_issues(segments: list[tuple[int, int]], limit: int, label: str) -> list[str]:
    issues = []
    if segments[0][0] != 0:
        issues.append(f"{label}: таймлайн должен начинаться с 0 с, а начинается с {segments[0][0]} с")
    for (a1, b1), (a2, b2) in zip(segments, segments[1:]):
        if a2 != b1:
            issues.append(f"{label}: разрыв или нахлёст в таймлайне между {a1}–{b1} и {a2}–{b2} с")
    for a, b in segments:
        if b <= a:
            issues.append(f"{label}: отрезок {a}–{b} с некорректен")
    if segments[-1][1] > limit:
        issues.append(f"{label}: таймлайн доходит до {segments[-1][1]} с, а ролик — {limit} с")
    return issues


def check_prompt(prompt: str, generator: str, seconds: int, refs: int = 0) -> list[str]:
    gen = GENERATORS.get(generator)
    if not gen:
        return [f"промпт: {t}" for t in tech_issues(prompt)]
    limit = clamp_seconds(generator, seconds)
    words = len(prompt.split())
    issues: list[str] = []
    if generator == "seedance":
        segs = [(int(a), int(b)) for a, b in SEEDANCE_SEGMENT.findall(prompt)]
        if not segs:
            issues.append("Seedance: нет таймлайна вида «0–3s: …»")
        else:
            issues += _segments_issues(segs, limit, "Seedance")
            if segs[-1][1] < limit:
                issues.append(f"Seedance: таймлайн заканчивается на {segs[-1][1]} с, а ролик — {limit} с")
        if refs and "@image" not in prompt.lower():
            issues.append("Seedance: есть референсы, но нет привязки «@Image1 = …»")
        if words > 400:
            issues.append(f"Seedance: промпт слишком длинный ({words} слов)")
    elif generator == "veo":
        stamps = [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in VEO_STAMP.findall(prompt)]
        if stamps:
            issues += _segments_issues(stamps, limit, "Veo")
        if words > 700:  # ≈1024 токена
            issues.append(f"Veo: промпт длиннее лимита ~1024 токенов ({words} слов)")
    elif words > 350:
        issues.append(f"{gen.name}: промпт слишком длинный ({words} слов)")
    issues += [f"{gen.name}: {t}" for t in tech_issues(prompt)]
    if re.search(r"[А-Яа-яЁё]{4,}", re.sub(r"\"[^\"]*\"|«[^»]*»", "", prompt)):
        issues.append(f"{gen.name}: промпт должен быть на английском (кириллица допустима только в репликах в кавычках)")
    return issues


def check_answer(text: str, generator: str, seconds: int, refs: int = 0) -> list[str]:
    """Проверяет все промпты в ответе; возвращает список нарушений с номером блока."""
    issues = []
    for i, block in enumerate(prompt_blocks(text), 1):
        issues += [f"блок {i}: {p}" for p in check_prompt(block, generator, seconds, refs)]
    return issues


# ---------- «гигиена» промптов: дизайнерская разметка не должна попадать в сцену ----------
# Генераторы воспринимают HEX-коды, CSS-термины и проценты как часть изображения и рисуют их надписями.

HYGIENE_RULE = (
    "ГИГИЕНА ПРОМПТОВ (обязательно для каждого блока ```prompt): генератор рисует всё написанное как часть "
    "сцены, поэтому внутри промптов ЗАПРЕЩЕНЫ: HEX/RGB-коды цветов (#ccdd00, rgb(…)) — называй цвет словами "
    "(«warm amber», «deep teal»); дизайнерские и CSS-термины (margin, padding, font-size, opacity, px, pt, "
    "safe zone) и проценты разметки («7% from the top») — описывай положение языком кино («in the lower third», "
    "«centered with empty space around»); названия шрифтов и файлов. НИКОГДА не проси «оставить место / "
    "placeholder / box / area / frame / safe zone» под логотип или текст и не задавай размеры и сетку макета — "
    "генератор рисует эти рамки, цифры и направляющие прямо на картинке. Если нужно свободное место, опиши его как "
    "часть сцены: «the upper part of the frame is plain, softly lit cream background with nothing in it». "
    "Текст на картинке — только если пользователь просил, точной фразой в кавычках, без указания размеров. "
    "HEX, отступы, сетка и шрифты допустимы только в описательной части ответа для дизайнера, вне блоков ```prompt."
)

HEX_RE = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z])")
RGB_RE = re.compile(r"\brgba?\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d.]+)?\s*\)", re.I)
CSS_RE = re.compile(r"\b(margins?|paddings?|font[- ]size|font[- ]weight|line[- ]height|letter[- ]spacing|"
                    r"opacity|z-index|border[- ]radius|safe[- ]zones?|kerning)\b", re.I)
_PH = (r"(?:place[- ]?holders?(?:\s+(?:box|frame|area|rectangle))?|bounding boxes?|text boxes?|"
       r"logo (?:box|area|space|zone|placeholder)|(?:empty|blank|reserved?) (?:box|frame|rectangle|area|space|zone)|"
       r"(?:space|area|room|zone) (?:for|reserved for) (?:the |a )?(?:logo|text|title|caption|copy|headline)|"
       r"(?:clear|empty|free|blank) (?:for|of) (?:the |a )?(?:logo|text|title|caption|copy|headline)s?|"
       r"guide ?lines?|layout grid|grid lines|rule of thirds grid|measurements?|rulers?|crop marks?|"
       r"dimension (?:lines|labels))")
PLACEHOLDER_RE = re.compile(rf"\b{_PH}\b", re.I)
UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:px|pt|rem|em|vh|vw)\b", re.I)
# Проценты считаем разметкой, только если рядом слова о положении/размере («7% from the top», «20% of the frame»)
PERCENT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s?%\s*(?:\w+\s+){0,3}?(?:from|of\s+the\s+(?:frame|screen|width|height|canvas)|top|bottom|"
    r"left|right|edges?|width|height|offset|inset|margins?|paddings?|spacing)\b"
    r"|\b(?:margins?|paddings?|offset|inset|spacing)\b\W*(?:\w+\W+){0,2}?\d+(?:\.\d+)?\s?%",
    re.I,
)


NO_MARKUP_SENTENCE = ("Empty areas are simply part of the scene's background, with no frames, boxes, outlines, guide "
                      "lines, rulers, numbers or measurement labels anywhere in the image.")


def tech_issues(prompt: str) -> list[str]:
    prompt = prompt.replace(NO_MARKUP_SENTENCE, "")  # наша собственная фраза-запрет — не нарушение
    found = []
    if HEX_RE.search(prompt) or RGB_RE.search(prompt):
        found.append("коды цветов (HEX/RGB) — замени названиями цветов")
    if CSS_RE.search(prompt) or UNIT_RE.search(prompt):
        found.append("дизайнерские термины/единицы (margin, padding, px…) — опиши положение словами")
    if PERCENT_RE.search(prompt):
        found.append("проценты разметки — опиши положение и размер словами")
    if PLACEHOLDER_RE.search(prompt):
        found.append("«место/рамка/placeholder под логотип или текст» — генератор нарисует рамку; "
                     "опиши свободную область как пустой фон сцены")
    return found


def _color_name(r: int, g: int, b: int) -> str:
    import colorsys

    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if s < 0.12 or l < 0.06 or l > 0.95:
        if l < 0.12:
            return "black"
        if l > 0.9:
            return "white"
        return "dark grey" if l < 0.4 else "light grey" if l > 0.7 else "grey"
    hue = h * 360
    names = [(15, "red"), (40, "orange"), (52, "amber"), (64, "yellow"), (85, "yellow-green"), (150, "green"),
             (180, "teal"), (200, "cyan"), (225, "sky blue"), (250, "blue"), (275, "indigo"), (295, "violet"),
             (320, "magenta"), (345, "pink"), (361, "red")]
    name = next(n for limit, n in names if hue < limit)
    if name in ("orange", "amber") and l < 0.35:
        name = "brown"
    if name in ("blue", "sky blue", "indigo") and l < 0.3:
        return "navy blue"
    tone = "deep " if l < 0.3 else "dark " if l < 0.42 else "pale " if l > 0.8 else "light " if l > 0.65 else ""
    muted = "muted " if s < 0.35 else ""
    return f"{tone}{muted}{name}"


def _hex_name(m: re.Match) -> str:
    code = m.group(0)[1:]
    if len(code) == 3:
        code = "".join(c * 2 for c in code)
    return _color_name(int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16))


_NUM = r"\d+(?:\.\d+)?\s?(?:%|px|pt|rem|em|vh|vw)"
_TERM = r"(?:margins?|paddings?|font[- ]size|font[- ]weight|line[- ]height|letter[- ]spacing|opacity|border[- ]radius|offset|inset)"
def _position_words(m: re.Match) -> str:
    n, side = float(m.group(1)), m.group(2).lower()
    if n <= 20:
        return f"near the {side} edge" if side in ("left", "right") else f"near the {side}"
    if n <= 40:
        third = {"top": "upper", "bottom": "lower", "left": "left", "right": "right"}[side]
        return f"in the {third} third"
    return "around the middle"


def _size_words(m: re.Match) -> str:
    n, what = float(m.group(1)), m.group(2).lower()
    what = "frame" if what in ("canvas", "screen", "width", "height") else what
    size = ("a small part" if n <= 12 else "about a quarter" if n <= 30 else "about a third" if n <= 42
            else "about half" if n <= 60 else "most")
    return f"{size} of the {what}"


POSITION_RE = re.compile(r"(?:(?:placed|positioned|located|set)\s+)?(\d+(?:\.\d+)?)\s?%\s+from\s+the\s+"
                         r"(top|bottom|left|right)(?:\s+edge)?", re.I)
SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s?%\s+of\s+the\s+(frame|screen|width|height|canvas|image)", re.I)
EMPTY_AREA = "plain, uncluttered background"
_FOR_TEXT = r"for\s+(?:the\s+|a\s+|an\s+)?(?:brand\s+)?(?:logo|text|title|caption|copy|headline|lettering)s?"
_LOCATION = (r"the\s+(?:(?:[\w-]+\s+){0,2}(?:corner|edge|side|third|area|part|half)|(?:top|bottom|left|right)(?:-\w+)?"
             r"(?:\s+(?:corner|edge|side|third|area|part|half))?)(?:\s+of\s+the\s+(?:frame|image|poster|screen))?")
RESERVE_RE = re.compile(
    rf"\b(?:reserve|leave|keep|allocate)\b[^.;]*?\b(?:in|at)\s+({_LOCATION})[^.;]*?\b{_FOR_TEXT}\b"
    rf"|\b(?:reserve|leave|keep|allocate)\b[^.;]*?\b{_FOR_TEXT}\b[^.;]*?\b(?:in|at)\s+({_LOCATION})"
    rf"|\b(?:keep|leave)\s+({_LOCATION})\s+(?:clear|empty|free|blank)(?:\s+{_FOR_TEXT})?", re.I)

LAYOUT_PHRASES = [
    # «with 10% padding from the top», «margin: 7% from the top», «padding 24px», «font-size 64px»
    re.compile(rf"\s*(?:,\s*)?(?:with\s+)?(?:an?\s+)?(?:{_NUM}\s+)?{_TERM}\b(?:\s*:?\s*(?:of\s+)?{_NUM})?"
               r"(?:\s*(?:from|around|on|at|to)\s+(?:the\s+|all\s+)?(?:top|bottom|left|right|edges?|sides?|frame|"
               r"screen|it)(?:\s+edge)?)?", re.I),
    # «placed 10% from the bottom edge», «20% of the frame»
    re.compile(rf"\s*(?:,\s*)?(?:(?:placed|positioned|located)\s+)?\d+(?:\.\d+)?\s?%\s+(?:from|of)\s+the\s+"
               rf"(?:top|bottom|left|right|frame|screen|width|height|canvas)(?:\s+edge)?", re.I),
    re.compile(rf"\s*(?:,\s*)?\b(?:at\s+)?\d+(?:\.\d+)?\s?(?:px|pt|rem|em|vh|vw)\b", re.I),
]


def sanitize(prompt: str) -> str:
    """Последняя страховка перед отправкой в генератор: коды цветов → названия, фразы разметки — вырезаются."""
    issues = tech_issues(prompt)
    if not issues:
        return prompt  # чистый промпт не трогаем
    had_sentence = NO_MARKUP_SENTENCE in prompt
    # любая разметка (кроме одних только цветов) — повод явно запретить рамки, цифры и направляющие
    had_markup = had_sentence or any("цвет" not in i for i in issues)
    text = HEX_RE.sub(_hex_name, prompt.replace(NO_MARKUP_SENTENCE, ""))
    text = RGB_RE.sub(lambda m: _color_name(*(min(255, int(v)) for v in m.groups())), text)
    text = RESERVE_RE.sub(lambda m: f"keep {m.group(1) or m.group(2) or m.group(3)} as {EMPTY_AREA}", text)
    text = POSITION_RE.sub(_position_words, text)  # «10% from the top» → «near the top»
    text = SIZE_RE.sub(_size_words, text)  # «20% of the frame» → «about a quarter of the frame»

    # «placeholder box for the logo» → «plain, uncluttered background»
    text = re.sub(rf"(?:\b(?:an?|the)\s+)?(?:(?:empty|blank|reserved)\s+)?\b{_PH}\b"
                  r"(?:\s+(?:for|reserved for)\s+(?:the\s+|a\s+)?(?:logo|text|title|caption|copy|headline))?",
                  EMPTY_AREA, text, flags=re.I)
    for pattern in LAYOUT_PHRASES:  # убираем сами фразы разметки (отступы, единицы)
        text = pattern.sub("", text)
    # Удаляем целые фрагменты (между знаками , ; . и переносами), где есть разметка
    parts = re.split(r"([,;.\n])", text)
    kept = []
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if CSS_RE.search(chunk) or UNIT_RE.search(chunk) or PERCENT_RE.search(chunk):
            if sep in ".\n" and kept and kept[-1].endswith(","):
                kept[-1] = kept[-1][:-1] + "."  # фраза закончилась на вырезанном фрагменте — ставим точку
            if sep == "\n":
                kept.append("\n")
            continue
        kept.append(chunk + sep)
    text = "".join(kept)
    text = re.sub(r"(?:(?<=[,.;])|^)\s*(?:a small part|about a quarter|about a third|about half|most) of the "
                  r"(?:frame|image)\s*(?=[,.;]|$)", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;])", r"\1", text)
    text = re.sub(r"([,;])\s*([.;])", r"\2", text)
    text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text.strip(" ,;"))
    if had_markup:  # явный запрет рисовать служебную разметку
        text = text.replace(NO_MARKUP_SENTENCE, "").rstrip() + " " + NO_MARKUP_SENTENCE
    return text.strip()


def sanitize_answer(text: str) -> str:
    """Чистит все блоки ```prompt внутри ответа (описательная часть не трогается)."""
    def fix(m: re.Match) -> str:
        lang, body = m.group(1), m.group(2)
        if lang.strip().lower() in ("srt", "json", "text"):
            return m.group(0)
        return f"```{lang}\n{sanitize(body).strip()}\n```"
    return CODE_BLOCK.sub(fix, text)
