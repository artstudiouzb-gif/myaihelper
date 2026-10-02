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
        return []
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
    if re.search(r"[А-Яа-яЁё]{4,}", re.sub(r"\"[^\"]*\"|«[^»]*»", "", prompt)):
        issues.append(f"{gen.name}: промпт должен быть на английском (кириллица допустима только в репликах в кавычках)")
    return issues


def check_answer(text: str, generator: str, seconds: int, refs: int = 0) -> list[str]:
    """Проверяет все промпты в ответе; возвращает список нарушений с номером блока."""
    issues = []
    for i, block in enumerate(prompt_blocks(text), 1):
        issues += [f"блок {i}: {p}" for p in check_prompt(block, generator, seconds, refs)]
    return issues
