"""Разделы бота: поля форм, промпты и логика каждого инструмента."""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from . import config
from .ai import images, llm, voice
from .ai.llm import AIError, Media

log = logging.getLogger(__name__)


@dataclass
class RunContext:
    values: dict[str, str]
    files: dict[str, list[Media]]
    provider: str
    lang: str

    def v(self, name: str, default: str = "") -> str:
        return self.values.get(name, "").strip() or default

    def f(self, name: str) -> list[Media]:
        return self.files.get(name, [])

    def flag(self, name: str) -> bool:
        return self.values.get(name) in ("1", "true", "on")


@dataclass
class Result:
    text: str = ""
    images: list[bytes] = field(default_factory=list)
    audio: bytes | None = None
    video: bytes | None = None


@dataclass
class Tool:
    id: str
    title: str
    subtitle: str
    icon: str  # имя SVG-иконки из webapp/app.js
    category: str  # scripts | prompts | visual | media
    fields: list[dict]
    system: str = ""
    task: str = ""
    run: Callable[["Tool", RunContext], Awaitable[Result]] | None = None
    uses_llm: bool = True  # показывать выбор модели (Claude / ChatGPT / Gemini)
    needs: tuple[str, ...] = ()  # обязательные ключи API
    hint: str = ""

    def public(self) -> dict:
        return {
            "id": self.id, "title": self.title, "subtitle": self.subtitle, "icon": self.icon,
            "category": self.category, "fields": self.fields, "uses_llm": self.uses_llm,
            "needs": self.needs, "hint": self.hint,
        }


# ---------- поля форм ----------


def text(name, label, placeholder="", required=False, **kw):
    return {"name": name, "label": label, "type": "text", "placeholder": placeholder, "required": required, **kw}


def area(name, label, placeholder="", required=False, **kw):
    return {"name": name, "label": label, "type": "textarea", "placeholder": placeholder, "required": required, **kw}


def select(name, label, options, default=None, **kw):
    opts = [o if isinstance(o, (list, tuple)) else (o, o) for o in options]
    return {"name": name, "label": label, "type": "select", "options": opts,
            "default": default if default is not None else opts[0][0], **kw}


def number(name, label, default, lo=1, hi=30, **kw):
    return {"name": name, "label": label, "type": "number", "default": default, "min": lo, "max": hi, **kw}


def files(name, label, accept, required=False, multiple=False, max_files=1, **kw):
    return {"name": name, "label": label, "type": "file", "accept": accept, "required": required,
            "multiple": multiple, "max": max_files, **kw}


def check(name, label, default=False, **kw):
    return {"name": name, "label": label, "type": "checkbox", "default": default, **kw}


ASPECTS = [("9:16", "9:16"), ("16:9", "16:9"), ("1:1", "1:1")]
OUT_LANGS = [("русский", "Русский"), ("узбекский", "Узбекский"), ("английский", "Английский"),
             ("казахский", "Казахский"), ("турецкий", "Турецкий")]

# ---------- общие промпты ----------

PRODUCER = (
    "Ты — опытный креативный продюсер, сценарист и режиссёр коротких вертикальных видео "
    "(Reels, TikTok, YouTube Shorts) и эксперт по AI-видео и AI-изображениям "
    "(Seedance, Kling, Veo, Sora, Runway, Hailuo, Grok Imagine, Midjourney, GPT Image, Nano Banana). "
    "Отвечаешь конкретно, без воды и общих советов, сразу готовым к использованию результатом."
)

LANG_NAMES = {"ru": "русском", "uz": "узбекском (латиница)", "en": "английском"}


def lang_rule(lang: str, prompts_in_english: bool = True) -> str:
    rule = (
        f"Пиши ответ на {LANG_NAMES.get(lang, 'русском')} языке. "
        "Оформляй в Markdown: заголовки ##, списки, **жирный**, таблицы при необходимости."
    )
    if prompts_in_english:
        rule += (
            " Промпты для нейросетей-генераторов (то, что пользователь будет копировать в генератор) "
            "пиши на английском и помещай каждый в отдельный блок кода ```, потому что генераторы "
            "лучше понимают английский. Реплики и закадровый текст — на языке, который укажет пользователь, "
            "а если не указал — на языке ответа."
        )
    return rule


def user_data(tool: Tool, ctx: RunContext) -> str:
    """Собирает заполненные пользователем текстовые поля в читаемый блок."""
    lines = []
    for f in tool.fields:
        if f["type"] in ("file", "checkbox"):
            continue
        value = ctx.v(f["name"])
        if f["type"] == "select":
            value = dict(f["options"]).get(value, value)
        if value:
            lines.append(f"- {f['label']}: {value}")
    return "\n".join(lines)


class _Defaults(dict):
    def __missing__(self, key: str) -> str:
        return ""


def build_prompt(tool: Tool, ctx: RunContext, task: str | None = None, attachments_note: str = "") -> str:
    task = (task or tool.task).format_map(_Defaults({k: ctx.v(k) for k in ctx.values}))
    parts = [task, "Данные от пользователя:\n" + (user_data(tool, ctx) or "- (не указаны)")]
    if attachments_note:
        parts.append(attachments_note)
    return "\n\n".join(parts)


def all_media(tool: Tool, ctx: RunContext) -> list[Media]:
    return [m for f in tool.fields if f["type"] == "file" for m in ctx.f(f["name"])]


async def run_text(tool: Tool, ctx: RunContext) -> Result:
    media = all_media(tool, ctx)
    note = "К сообщению приложены файлы пользователя — внимательно изучи их." if media else ""
    system = f"{PRODUCER}\n\n{tool.system}\n\n{lang_rule(ctx.lang)}".strip()
    answer = await llm.generate_text(ctx.provider, system, build_prompt(tool, ctx, attachments_note=note), media)
    return Result(text=answer)


def extract_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise AIError("Модель вернула ответ в неожиданном формате. Попробуйте ещё раз.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise AIError("Модель вернула некорректный JSON. Попробуйте ещё раз.") from e


def image_engine(preferred: str = "") -> str:
    providers = config.available_providers()
    if preferred in ("gemini", "openai") and providers[preferred]:
        return preferred
    if providers["gemini"]:
        return "gemini"
    if providers["openai"]:
        return "openai"
    raise AIError("Для генерации изображений нужен ключ Gemini или OpenAI.")


async def gather_images(coros: list[Awaitable[list[bytes]]]) -> tuple[list[bytes], int]:
    """Запускает генерации параллельно; возвращает картинки и число неудачных попыток.
    Если не получилось ни одной — пробрасывает первую ошибку."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    out, errors = [], []
    for r in results:
        if isinstance(r, BaseException):
            log.warning("image generation failed: %r", r)
            errors.append(r)
        else:
            out.extend(r)
    if errors and not out:
        raise errors[0]
    return out, len(errors)


# ---------- нестандартные разделы ----------

VIDEO_STUDY_TASKS = {
    "full": (
        "Полностью разбери приложенное видео:\n"
        "## 1. О чём видео — 2–3 предложения.\n"
        "## 2. Транскрипт речи с таймкодами [мм:сс] на языке оригинала.\n"
        "## 3. Перевод речи на {target_lang} язык (с таймкодами).\n"
        "## 4. Раскадровка: для каждой сцены — таймкод, что в кадре, крупность плана, ракурс, движение камеры, свет, эмоция.\n"
        "## 5. Промпты для AI-видео генератора на каждую сцену, чтобы пересоздать это видео"
        " (если пользователь описал нового персонажа или приложил его фото — с этим персонажем).\n"
        "## 6. Почему это видео работает: хук, ритм, монтаж, что можно улучшить."
    ),
    "translate": (
        "Сделай перевод приложенного видео:\n"
        "## 1. Транскрипт речи с таймкодами [мм:сс] на языке оригинала (с указанием говорящих).\n"
        "## 2. Дословный перевод на {target_lang} язык с теми же таймкодами.\n"
        "## 3. Адаптированный текст для дубляжа (язык: {target_lang}): естественная живая речь, "
        "каждая реплика по длине укладывается в свой таймкод. Дай его одним блоком, готовым для озвучки.\n"
        "В конце подскажи: озвучить текст можно в разделе «Голоса»."
    ),
    "replace": (
        "Подготовь замену персонажа в приложенном видео:\n"
        "## 1. Подробное описание исходного персонажа (внешность, одежда, манера).\n"
        "## 2. Новый персонаж: по описанию пользователя и/или приложенному фото — максимально "
        "детальное описание внешности для консистентной генерации (character sheet).\n"
        "## 3. Покадровая раскадровка с таймкодами, и для каждой сцены — промпт для AI-видео, где "
        "всё (движения, камера, свет, фон, тайминг) как в оригинале, но в кадре новый персонаж.\n"
        "## 4. Промпт для редактирования первого кадра (image edit: заменить персонажа), чтобы "
        "использовать его как стартовый кадр в image-to-video.\n"
        "## 5. Транскрипт реплик персонажа с таймкодами."
    ),
}


async def run_video_study(tool: Tool, ctx: RunContext) -> Result:
    task = VIDEO_STUDY_TASKS.get(ctx.v("mode"), VIDEO_STUDY_TASKS["full"])
    system = f"{PRODUCER}\n\nТы внимательно анализируешь видео, точно расставляешь таймкоды.\n\n{lang_rule(ctx.lang)}"
    note = "Первый файл — видео. Если есть изображение — это фото нового персонажа."
    answer = await llm.generate_text("gemini", system, build_prompt(tool, ctx, task, note), all_media(tool, ctx))
    return Result(text=answer)


async def run_image(tool: Tool, ctx: RunContext) -> Result:
    prompt, refs = ctx.v("prompt"), ctx.f("refs")
    note = ""
    if ctx.flag("enhance"):
        system = (
            "Ты — эксперт по промптам для генерации изображений. Перепиши запрос пользователя в один "
            "детальный промпт на английском: объект, композиция, ракурс, объектив, свет, стиль, "
            "цветовая палитра, детализация. Если приложены референсы — опиши, как их использовать. "
            "Верни ТОЛЬКО сам промпт, без пояснений и кавычек."
        )
        prompt = await llm.generate_text(ctx.provider, system, prompt, refs)
        note = f"**Улучшенный промпт:**\n```\n{prompt}\n```"
    engine = image_engine(ctx.v("engine"))
    tasks = [images.generate_image(engine, prompt, refs, ctx.v("size", "1024x1024"))
             for _ in range(int(ctx.v("count", "1")))]
    imgs, failed = await gather_images(tasks)
    if failed:
        note += f"\n\n⚠️ Не удалось сгенерировать {failed} из {len(tasks)}."
    return Result(text=note.strip(), images=imgs)


async def run_motion(tool: Tool, ctx: RunContext) -> Result:
    media = ctx.f("media")
    if not media and not ctx.v("script"):
        raise AIError("Загрузите видео/аудио или вставьте текст сценария.")
    return await run_text(tool, ctx)


async def run_angles(tool: Tool, ctx: RunContext) -> Result:
    frame = ctx.f("frame")
    count = int(ctx.v("count", "4"))
    system = (
        f"{PRODUCER}\n\nТы — оператор-постановщик. По одному кадру ты придумываешь новые ракурсы "
        "той же сцены, как будто её снимали несколькими камерами одновременно."
    )
    lang = LANG_NAMES.get(ctx.lang, "русском")
    prompt = (
        f"Изучи кадр и предложи {count} новых ракурсов этой же сцены (тот же момент, те же персонажи, "
        "одежда, окружение и свет). Разнообразь: крупность (общий, средний, крупный, деталь), "
        "высоту (нижний, верхний, на уровне глаз), позицию (через плечо, профиль, сзади, POV).\n"
        + (f"Пожелания пользователя: {ctx.v('wishes')}\n" if ctx.v("wishes") else "")
        + "Верни ТОЛЬКО JSON без пояснений в формате:\n"
        '{"scene": "описание исходного кадра", "angles": [{"name": "название ракурса", '
        '"why": "зачем этот ракурс в монтаже", "image_prompt": "English prompt for regenerating '
        'this exact scene from the new angle", "video_prompt": "English image-to-video prompt, '
        '5 seconds, camera and subject motion"}]}\n'
        f"Поля scene, name и why пиши на {lang} языке."
    )
    data = extract_json(await llm.generate_text(ctx.provider, system, prompt, frame))
    angles = data.get("angles", [])[:count]

    md = [f"## Исходный кадр\n{data.get('scene', '')}"]
    for i, a in enumerate(angles, 1):
        md.append(
            f"## {i}. {a.get('name', '')}\n{a.get('why', '')}\n\n**Промпт кадра:**\n```\n{a.get('image_prompt', '')}\n```"
            f"\n**Промпт для анимации:**\n```\n{a.get('video_prompt', '')}\n```"
        )

    imgs: list[bytes] = []
    if ctx.flag("generate") and angles:
        engine = image_engine()
        tasks = [
            images.generate_image(
                engine,
                "Using the reference image, show the exact same scene, characters, clothing, environment, "
                f"lighting and style from a different camera angle: {a.get('image_prompt', '')}",
                frame,
                "1024x1536" if ctx.v("aspect") == "9:16" else "1536x1024" if ctx.v("aspect") == "16:9" else "1024x1024",
            )
            for a in angles
        ]
        try:
            imgs, failed = await gather_images(tasks)
            if failed:
                md.append(f"⚠️ Не удалось сгенерировать {failed} изображ. из {len(tasks)}.")
        except Exception as e:  # промпты всё равно полезны — отдаём их
            md.append(f"⚠️ Изображения не сгенерировались: {e}")
    return Result(text="\n\n".join(md), images=imgs)


async def run_voices(tool: Tool, ctx: RunContext) -> Result:
    mode = ctx.v("mode", "tts")
    if mode == "tts":
        if not ctx.v("text"):
            raise AIError("Введите текст для озвучки.")
        return Result(audio=await voice.text_to_speech(ctx.v("voice"), ctx.v("text")))

    if mode == "sts":
        src = ctx.f("source")
        if not src:
            raise AIError("Загрузите аудио или видео с речью.")
        audio = await voice.to_audio(src[0])
        new_audio = await voice.speech_to_speech(ctx.v("voice"), audio, ctx.flag("denoise"))
        if src[0].is_video and ctx.flag("keep_video"):
            return Result(video=await voice.replace_audio(src[0], new_audio), audio=new_audio)
        return Result(audio=new_audio)

    if mode == "clone":
        samples = ctx.f("samples")
        if not samples:
            raise AIError("Загрузите хотя бы один образец голоса (лучше 1–3 минуты чистой речи).")
        name = ctx.v("name", "Мой голос")
        voice_id = await voice.clone_voice(name, samples, ctx.flag("denoise"))
        result = Result(text=f"✅ Голос **{name}** создан и уже доступен в списке голосов.\n\nID: `{voice_id}`")
        if ctx.v("preview"):
            result.audio = await voice.text_to_speech(voice_id, ctx.v("preview"))
        return result

    raise AIError("Неизвестный режим.")


async def run_character(tool: Tool, ctx: RunContext) -> Result:
    photos = ctx.f("photos")
    system = f"{PRODUCER}\n\nТы — художник по персонажам и кастинг-директор.\n\n{lang_rule(ctx.lang)}"
    prompt = build_prompt(
        tool, ctx,
        "По приложенным фото составь карточку персонажа для консистентной AI-генерации:\n"
        "## Имя и роль\n## Внешность — максимально подробно: возраст, тип лица, глаза, брови, нос, губы, "
        "кожа, волосы (цвет, длина, укладка), телосложение, рост, особые приметы\n"
        "## Одежда и стиль\n## Характер, манера двигаться и говорить, голос\n"
        "## Промпт персонажа — 60–90 слов на английском, который можно вставлять в каждый промпт "
        "для узнаваемости\n## Negative prompt — чего избегать\n"
        "## Как использовать: советы для Seedance/Kling/Veo/Nano Banana, чтобы персонаж не менялся.",
        "Приложены фото персонажа (до 3 шт.).",
    )
    jobs: list[Awaitable] = [llm.generate_text(ctx.provider, system, prompt, photos)]
    if ctx.flag("sheet"):
        sheet_prompt = (
            "Create a professional character reference sheet of this exact person from the reference photos. "
            "Layout on a clean light-grey studio background: full-body front view, side view and back view in a row, "
            "plus three head close-ups with neutral, smiling and serious expressions. Identical face, hairstyle, "
            "body and outfit in every view, soft even studio lighting, photorealistic, sharp details, thin dividers "
            "between panels, no text." + (f" Extra details: {ctx.v('notes')}" if ctx.v("notes") else "")
        )
        jobs.append(images.generate_image(image_engine(ctx.v("engine")), sheet_prompt, photos, "1536x1024"))
    results = await asyncio.gather(*jobs, return_exceptions=True)
    if isinstance(results[0], BaseException):
        raise results[0]
    result = Result(text=results[0])
    if len(results) > 1:
        if isinstance(results[1], BaseException):
            log.warning("character sheet failed: %s", results[1])
            result.text += f"\n\n⚠️ Не удалось нарисовать карточку: {results[1]}"
        else:
            result.images = results[1]
    return result


# ---------- список разделов ----------

TOOLS: list[Tool] = [
    Tool(
        "ideas", "Генератор идей", "Вирусные идеи по теме", "bulb", "scripts",
        [
            area("topic", "Тема или ниша", "Например: кофейня в Ташкенте, фитнес для мам, AI-новости", True),
            text("audience", "Целевая аудитория", "Кто будет смотреть (необязательно)"),
            select("platform", "Платформа", ["Instagram Reels", "TikTok", "YouTube Shorts", "Все платформы"]),
            number("count", "Сколько идей", 10, 3, 30),
        ],
        system="Ты генерируешь идеи, которые реально набирают охваты, а не банальности.",
        task=(
            "Сгенерируй {count} идей для коротких вертикальных видео. Для каждой идеи:\n"
            "- **Название**\n- **Хук** — первая фраза и первый кадр (первые 3 секунды)\n"
            "- **Суть** — сюжет в 3–5 предложениях\n- **Почему залетит** — какой триггер (эмоция, спор, "
            "польза, узнаваемость, любопытство)\n- **Формат** — говорящая голова / AI-видео / сторителлинг / тренд\n"
            "- **Промпт для AI-видео**, если идея подходит для генерации.\n"
            "В конце — топ-3 идеи, с которых стоит начать, и почему."
        ),
    ),
    Tool(
        "hooks", "Вирусные хуки", "Удержание в первые 3 секунды", "magnet", "scripts",
        [
            area("topic", "О чём видео", "Кратко опишите видео или вставьте сценарий", True),
            select("style", "Тип хуков", ["Смешанные", "Интрига", "Шок / провокация", "Вопрос",
                                          "Боль аудитории", "Цифры и факты", "История"]),
            number("count", "Сколько хуков", 15, 5, 40),
        ],
        system="Ты — специалист по удержанию внимания в первые 3 секунды видео.",
        task=(
            "Напиши {count} хуков для этого видео. Для каждого: **текст хука** (что сказать, до 12 слов), "
            "**визуал** первых 3 секунд, **надпись на экране**, **тип триггера**. Сгруппируй по типам. "
            "В конце отметь 3 самых сильных хука и объясни почему."
        ),
    ),
    Tool(
        "video_study", "Разбор видео", "Перевод и замена персонажа", "scan", "media",
        [
            files("video", "Видео", "video/*", required=True),
            select("mode", "Что сделать", [("full", "Полный разбор + промпты"), ("translate", "Перевод речи"),
                                          ("replace", "Замена персонажа")]),
            select("target_lang", "Язык перевода", OUT_LANGS),
            area("new_character", "Новый персонаж", "Опишите, на кого заменить (необязательно)"),
            files("character_photo", "Фото нового персонажа", "image/*"),
        ],
        run=run_video_study, uses_llm=False, needs=("gemini",),
        hint="Видео анализирует Gemini. Лучше загружать ролики до 2–3 минут.",
    ),
    Tool(
        "stories", "Stories и Reels", "Мини-серии и контент-план", "phone", "scripts",
        [
            area("niche", "Ниша и о чём блог", "Например: стоматология, личный бренд дизайнера", True),
            select("goal", "Что нужно", ["Контент-план для Reels", "Мини-сериал в Stories",
                                         "Прогрев к продаже в Stories", "Reels-рубрика (серия роликов)"]),
            select("period", "Период", ["7 дней", "14 дней", "30 дней"]),
            text("product", "Продукт / цель", "Что продаём или какая цель (необязательно)"),
        ],
        system="Ты — SMM-стратег, который строит контент на сериальности и клиффхэнгерах.",
        task=(
            "Составь план под задачу пользователя. Для контент-плана — таблица: день | формат | тема | хук | "
            "CTA. Для Stories — по дням: каждая сторис (кадр, текст на экране, интерактив: опрос/вопрос/слайдер) "
            "и клиффхэнгер в конце дня. Для рубрики — концепция, оформление и сценарии выпусков. "
            "Добавь промпты для AI-видео/изображений там, где они помогут."
        ),
    ),
    Tool(
        "seedance", "Seedance промпт", "Профессиональный режиссёрский промпт", "zap", "prompts",
        [
            area("idea", "Идея сцены", "Что должно происходить в видео", True),
            select("duration", "Длительность", ["5 секунд", "10 секунд", "15 секунд"], "10 секунд"),
            select("aspect", "Формат", ASPECTS),
            text("style", "Стиль", "Например: кинематографичный, аниме, реклама, документальный"),
            files("ref", "Референс (персонаж или стиль)", "image/*"),
        ],
        system="Ты пишешь промпты уровня профессионального режиссёра и оператора для Seedance (ByteDance).",
        task=(
            "Напиши режиссёрский промпт для Seedance. Сначала раскадровка по шотам с таймкодами "
            "([0–3s], [3–6s] …): крупность плана, движение камеры (dolly in, orbit, crane, handheld, FPV), "
            "объектив, действие, свет, цветокоррекция, атмосфера, звук. Затем **финальный промпт** одним "
            "блоком на английском. Потом — чего избегать, и 2 альтернативы: более динамичная и более "
            "атмосферная. Если приложен референс — персонаж и стиль должны с ним совпадать."
        ),
    ),
    Tool(
        "minidrama", "Мини-драма", "Вертикальный сериал из 5 серий", "clapper", "scripts",
        [
            area("premise", "Завязка", "О чём сериал, кто герои", True),
            select("genre", "Жанр", ["Романтика", "Семейная драма", "Месть", "Триллер", "Комедия",
                                     "Мистика", "Бизнес / успех"]),
            select("length", "Длина серии", ["30 секунд", "60 секунд", "90 секунд"], "60 секунд"),
            text("dialog_lang", "Язык диалогов", "Например: узбекский"),
        ],
        system="Ты — шоураннер вертикальных мини-сериалов, которые смотрят запоем.",
        task=(
            "Создай вертикальный мини-сериал из 5 серий.\n"
            "Сначала: название, логлайн, персонажи — для каждого подробная внешность и одежда "
            "(одинаковое описание будем использовать во всех промптах) и промпт для character sheet.\n"
            "Для каждой серии: название, сцены с таймкодами, диалоги, клиффхэнгер в конце и "
            "промпт для AI-видео на каждую сцену (8–10 секунд) с одинаковыми описаниями персонажей."
        ),
    ),
    Tool(
        "serial", "Создание сериала", "Связанные 10-секундные промпты", "layers", "prompts",
        [
            area("story", "История", "Перескажите сюжет целиком", True),
            number("scenes", "Количество сцен", 6, 2, 20),
            area("character", "Персонажи", "Внешность героев (необязательно — придумаем)"),
            text("style", "Визуальный стиль", "Например: кино 35мм, Pixar 3D, аниме"),
            files("ref", "Референс персонажа", "image/*"),
        ],
        system="Ты отвечаешь за непрерывность (continuity) AI-сериала: персонажи и мир не должны «плыть».",
        task=(
            "Разбей историю на {scenes} связанных 10-секундных сцен для AI-видео (Seedance/Kling/Veo).\n"
            "Начни с блоков **Character bible** и **Style bible** (на английском).\n"
            "Для каждой сцены: описание, промпт на английском (дословно повторяй блок персонажа и стиля в "
            "каждом промпте), **последний кадр** — его можно использовать как стартовый кадр следующей "
            "сцены, и реплика/закадровый текст. Каждая сцена продолжает предыдущую без скачков."
        ),
    ),
    Tool(
        "grok", "Промпты для Grok", "Кадры, как в кино", "aperture", "prompts",
        [
            area("idea", "Идея", "Что должно быть в кадрах", True),
            select("genre", "Жанр", ["Драма", "Боевик", "Нуар", "Фантастика", "Хоррор", "Романтика",
                                     "Исторический", "Реклама"]),
            number("count", "Сколько кадров", 6, 1, 20),
        ],
        system="Ты — оператор-постановщик голливудского уровня и знаешь, как писать промпты для Grok Imagine.",
        task=(
            "Напиши {count} промптов для Grok Imagine, чтобы кадры выглядели как из большого кино. "
            "Для каждого: название кадра, **промпт изображения** (subject, action, composition, lens — "
            "например 35mm / anamorphic, lighting, color grade, film stock, mood) и **промпт анимации** "
            "(движение камеры и героя, ~6 секунд)."
        ),
    ),
    Tool(
        "image", "GPT Image", "Картинка из текста или по референсу", "image", "visual",
        [
            area("prompt", "Что нарисовать", "Опишите изображение", True),
            files("refs", "Референсы", "image/*", multiple=True, max_files=4),
            select("engine", "Генератор", [("openai", "GPT Image (OpenAI)"), ("gemini", "Nano Banana (Gemini)")]),
            select("size", "Формат", [("1024x1536", "Вертикальный 2:3"), ("1024x1024", "Квадрат 1:1"),
                                      ("1536x1024", "Горизонтальный 3:2")]),
            select("count", "Вариантов", ["1", "2", "3", "4"]),
            check("enhance", "Улучшить промпт с помощью ИИ", True),
        ],
        run=run_image,
    ),
    Tool(
        "motion", "Видео-анимация", "Моушн-дизайн под каждую фразу", "sparkles", "visual",
        [
            files("media", "Видео или аудио с речью", "video/*,audio/*"),
            area("script", "…или текст сценария", "Если нет видео — вставьте текст"),
            select("style", "Стиль", ["Kinetic typography", "Минимализм", "Яркий поп", "Неон / техно",
                                      "Корпоративный", "Документальный"]),
            select("aspect", "Формат", ASPECTS),
        ],
        system="Ты — моушн-дизайнер, который делает анимации для говорящих голов и экспертных роликов.",
        task=(
            "Сделай план моушн-дизайна. Если приложено видео или аудио — расшифруй речь и разбей на фразы "
            "с точными таймкодами. Для каждой фразы: таймкод, текст, ключевое слово-акцент, анимация "
            "(kinetic type, pop-up иконка, счётчик, подчёркивание, стрелки, B-roll и т.д.), элементы на экране, "
            "переход, звук (SFX).\nЗатем: общий стиль (шрифты, палитра в HEX, скорость анимаций), как собрать в "
            "CapCut и в After Effects, промпты для AI-генерации анимированных вставок. "
            "В конце — субтитры в формате SRT в блоке кода."
        ),
        run=run_motion,
        hint="Если загрузите видео или аудио, его расшифрует Gemini.",
    ),
    Tool(
        "angles", "Ракурсы камеры", "Новые ракурсы из одного дубля", "video", "visual",
        [
            files("frame", "Кадр из видео (скриншот)", "image/*", required=True),
            select("count", "Сколько ракурсов", ["3", "4", "6"], "4"),
            select("aspect", "Формат", ASPECTS),
            area("wishes", "Пожелания", "Например: нужен крупный план рук и общий план сверху"),
            check("generate", "Сгенерировать изображения ракурсов", True),
        ],
        run=run_angles,
        hint="Полученные кадры можно анимировать в Seedance/Kling по промптам анимации.",
    ),
    Tool(
        "voices", "Голоса", "Озвучка, клон и замена голоса", "mic", "media",
        [
            select("mode", "Режим", [("tts", "Озвучить текст"), ("sts", "Заменить голос в аудио/видео"),
                                     ("clone", "Клонировать голос")]),
            {"name": "voice", "label": "Голос", "type": "voice", "required": True,
             "show_if": {"mode": ["tts", "sts"]}},
            area("text", "Текст", "Текст для озвучки", show_if={"mode": ["tts"]}),
            files("source", "Аудио или видео с речью", "audio/*,video/*", show_if={"mode": ["sts"]}),
            check("keep_video", "Вернуть видео с новым голосом", True, show_if={"mode": ["sts"]}),
            text("name", "Название голоса", "Например: Мой голос", show_if={"mode": ["clone"]}),
            files("samples", "Образцы голоса", "audio/*,video/*", multiple=True, max_files=5,
                  show_if={"mode": ["clone"]}),
            area("preview", "Тестовая фраза", "Озвучим ей новый голос (необязательно)",
                 show_if={"mode": ["clone"]}),
            check("denoise", "Убрать фоновый шум", False, show_if={"mode": ["sts", "clone"]}),
        ],
        run=run_voices, uses_llm=False, needs=("elevenlabs",),
        hint="Работает через ElevenLabs. Клонирование доступно на платных тарифах ElevenLabs.",
    ),
    Tool(
        "character", "Карточка персонажа", "Карточка из 3 фото", "user", "visual",
        [
            files("photos", "Фото персонажа (до 3)", "image/*", required=True, multiple=True, max_files=3),
            text("name", "Имя персонажа", "Необязательно"),
            area("notes", "Дополнительно", "Роль, характер, во что одеть"),
            check("sheet", "Нарисовать character sheet", True),
            select("engine", "Генератор картинки", [("gemini", "Nano Banana (Gemini)"), ("openai", "GPT Image (OpenAI)")]),
        ],
        run=run_character,
    ),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}


def field_visible(f: dict, values: dict[str, str]) -> bool:
    cond = f.get("show_if")
    return not cond or all(values.get(k) in allowed for k, allowed in cond.items())


async def run_tool(tool: Tool, ctx: RunContext) -> Result:
    providers = config.available_providers()
    for need in tool.needs:
        llm.require(need)
    for f in tool.fields:
        if f.get("required") and field_visible(f, ctx.values):
            filled = ctx.f(f["name"]) if f["type"] == "file" else ctx.v(f["name"])
            if not filled:
                raise AIError(f"Заполните поле «{f['label']}».")
    if tool.uses_llm and not providers.get(ctx.provider):
        ctx.provider = next((p for p in ("claude", "openai", "gemini") if providers[p]), ctx.provider)
    return await (tool.run or run_text)(tool, ctx)
