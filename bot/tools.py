"""Разделы бота: поля форм, промпты и логика каждого инструмента."""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from . import config, prompt_rules
from .ai import images, llm, media, subtitles, video, voice
from .ai.llm import AIError, Media

log = logging.getLogger(__name__)


@dataclass
class RunContext:
    values: dict[str, str]
    files: dict[str, list[Media]]
    provider: str
    lang: str
    character: str = ""  # промпт персонажа из библиотеки
    character_media: list[Media] = field(default_factory=list)
    refine: dict | None = None  # контекст для «Доработать»: system, prompt, provider

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
    # Кнопки перехода в другие разделы: {label, tool, values, files: {поле: {"image": i} | {"from_field": имя}}}
    followups: list[dict] = field(default_factory=list)
    character: dict | None = None  # данные для сохранения персонажа в библиотеку


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
    generator: str = ""  # под какой генератор пишутся промпты (иначе — из поля target)
    seconds_field: str = ""  # поле с длительностью ролика/сцены
    character: bool = False  # можно подставить персонажа из библиотеки

    def public(self) -> dict:
        return {
            "id": self.id, "title": self.title, "subtitle": self.subtitle, "icon": self.icon,
            "category": self.category, "fields": self.fields, "uses_llm": self.uses_llm,
            "needs": self.needs, "hint": self.hint, "character": self.character,
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

# Языки дубляжа ElevenLabs Dubbing v2 (поддерживает 90+ языков; здесь — самые нужные)
DUB_LANGS = [("uz", "Узбекский"), ("ru", "Русский"), ("en", "Английский"), ("kk", "Казахский"),
             ("ky", "Киргизский"), ("tg", "Таджикский"), ("tk", "Туркменский"), ("az", "Азербайджанский"),
             ("tr", "Турецкий"), ("uk", "Украинский"), ("fa", "Персидский"), ("ar", "Арабский"),
             ("hi", "Хинди"), ("ur", "Урду"), ("de", "Немецкий"), ("fr", "Французский"), ("es", "Испанский"),
             ("it", "Итальянский"), ("pt", "Португальский"), ("pl", "Польский"), ("zh", "Китайский"),
             ("ja", "Японский"), ("ko", "Корейский"), ("id", "Индонезийский"), ("vi", "Вьетнамский"),
             ("th", "Тайский"), ("mn", "Монгольский")]

# ---------- общие промпты ----------

PRODUCER = (
    "Ты — опытный креативный продюсер, сценарист и режиссёр коротких вертикальных видео "
    "(Reels, TikTok, YouTube Shorts) и эксперт по AI-видео и AI-изображениям "
    "(Seedance, Kling, Veo, Gemini Omni, Runway, Hailuo, Grok Imagine, Midjourney, GPT Image, Nano Banana). "
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
            "пиши на английском, каждый — в отдельном блоке кода с пометкой ```prompt. Вспомогательные "
            "английские блоки (character bible, style bible, negative prompt) помечай ```text. "
            "Реплики героев — в кавычках на языке, который укажет пользователь (а если не указал — на языке ответа).\n"
            + prompt_rules.HYGIENE_RULE
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
    if ctx.character:
        parts.append(character_block(ctx))
    if attachments_note:
        parts.append(attachments_note)
    return "\n\n".join(parts)


def character_block(ctx: RunContext) -> str:
    return (
        "Главный персонаж из библиотеки пользователя. Используй это описание дословно (на английском) "
        "в каждом промпте, где он появляется, чтобы внешность не менялась"
        + (" — его фото тоже приложены" if ctx.character_media else "")
        + f":\n{ctx.character}"
    )


def all_media(tool: Tool, ctx: RunContext) -> list[Media]:
    own = [m for f in tool.fields if f["type"] == "file" for m in ctx.f(f["name"])]
    return own + ctx.character_media


async def ask(ctx: RunContext, system: str, prompt: str, media: list[Media] | None = None,
              provider: str | None = None) -> str:
    """Запрос к текстовой модели с сохранением контекста для кнопки «Доработать»."""
    provider = provider or ctx.provider
    answer = await llm.generate_text(provider, system, prompt, media)
    ctx.refine = {"system": system, "prompt": prompt, "provider": provider}
    return answer


def target_of(tool: Tool, ctx: RunContext) -> tuple[str, int]:
    """Генератор и длительность, под которые пишутся промпты в этом запросе."""
    generator = tool.generator or ctx.v("target")
    seconds = int(re.sub(r"\D", "", ctx.v(tool.seconds_field)) or 8) if tool.seconds_field else 8
    return generator, (prompt_rules.clamp_seconds(generator, seconds) if generator else seconds)


async def enforce_format(ctx: RunContext, system: str, answer: str, generator: str, seconds: int,
                         refs: int) -> str:
    """Проверяет промпты в ответе по правилам генератора; при нарушениях один раз просит модель исправить."""
    issues = prompt_rules.check_answer(answer, generator, seconds, refs)
    if not issues:
        return prompt_rules.sanitize_answer(answer)
    log.info("prompt format issues (%s): %s", generator, issues)
    fixed = await llm.generate_text(
        ctx.refine["provider"] if ctx.refine else ctx.provider, system,
        "Ниже твой ответ. Автоматическая проверка нашла нарушения формата промптов:\n- "
        + "\n- ".join(issues)
        + "\n\nИсправь ВСЕ нарушения и верни ПОЛНЫЙ исправленный ответ целиком, в том же оформлении, "
        "без комментариев об исправлениях.\n\n## Ответ\n" + answer,
    )
    fixed = prompt_rules.sanitize_answer(fixed)  # коды цветов и разметку убираем в любом случае
    left = prompt_rules.check_answer(fixed, generator, seconds, refs)
    if left:
        fixed += "\n\n⚠️ Автопроверка формата: " + "; ".join(left)
    return fixed


async def run_text(tool: Tool, ctx: RunContext) -> Result:
    media = all_media(tool, ctx)
    note = "К сообщению приложены файлы пользователя — внимательно изучи их." if media else ""
    generator, seconds = target_of(tool, ctx)
    rules = f"\n\n{prompt_rules.rules_for(generator, seconds)}" if generator else ""
    system = f"{PRODUCER}\n\n{tool.system}{rules}\n\n{lang_rule(ctx.lang)}".strip()
    answer = await ask(ctx, system, build_prompt(tool, ctx, attachments_note=note), media)
    refs = len([m for m in media if m.is_image])
    answer = await enforce_format(ctx, system, answer, generator, seconds, refs)
    return Result(text=answer)


REFINE_TASK = (
    "Ниже — исходная задача пользователя и твой предыдущий ответ. Доработай ответ по новой просьбе. "
    "Верни ПОЛНЫЙ обновлённый результат целиком в том же формате — без вступлений и без пересказа изменений."
)


async def refine(context: dict, previous: str, instruction: str) -> str:
    prompt = (
        f"{REFINE_TASK}\n\n## Исходная задача\n{context['prompt']}\n\n"
        f"## Предыдущий ответ\n{previous}\n\n## Что изменить\n{instruction}"
    )
    provider = context["provider"]
    if not config.available_providers().get(provider):
        provider = next(p for p in ("claude", "openai", "gemini") if config.available_providers()[p])
    return await llm.generate_text(provider, context["system"], prompt)


def extract_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise AIError("Модель вернула ответ в неожиданном формате. Попробуйте ещё раз.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise AIError("Модель вернула некорректный JSON. Попробуйте ещё раз.") from e


def image_engine(preferred: str = "") -> str:
    """Выбранный генератор, а если для него нет ключа — любой доступный."""
    providers = config.available_providers()
    if preferred in images.ENGINES and providers[images.provider_of(preferred)]:
        return preferred
    for engine in ("nb2", "flare"):
        if providers[images.provider_of(engine)]:
            return engine
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


ANIM_MARK = "ANIMATION_PROMPT:"
LANG_CODES = {"русский": "ru", "узбекский": "uz", "английский": "en", "казахский": "kk", "турецкий": "tr"}


async def run_video_study(tool: Tool, ctx: RunContext) -> Result:
    mode = ctx.v("mode", "full")
    task = VIDEO_STUDY_TASKS.get(mode, VIDEO_STUDY_TASKS["full"])
    if mode == "replace":
        task += (
            f"\n\nВ самом конце ответа отдельной строкой выведи «{ANIM_MARK} <промпт на английском для "
            "image-to-video: действие и движение героя и камеры на протяжении всего ролика, без описания внешности>»."
        )
    generator = ctx.v("target", "veo")
    seconds = prompt_rules.GENERATORS.get(generator, prompt_rules.GENERATORS["veo"]).max_seconds
    seconds = min(seconds, 8 if generator == "veo" else 15)
    rules = prompt_rules.rules_for(generator, seconds) if mode != "translate" else ""
    system = (f"{PRODUCER}\n\nТы внимательно анализируешь видео, точно расставляешь таймкоды. "
              f"Промпты сцен — не длиннее {seconds} с каждая.\n\n{rules}\n\n{lang_rule(ctx.lang)}")
    note = "Первый файл — видео. Изображения (если есть) — фото нового персонажа."
    answer = await ask(ctx, system, build_prompt(tool, ctx, task, note), all_media(tool, ctx), provider="gemini")
    answer = await enforce_format(ctx, system, answer, generator if rules else "", seconds, 0)

    anim = ""
    found = re.search(rf"{ANIM_MARK}\s*(.+)", answer)
    if found:
        anim = found.group(1).strip().strip("`*« »")
        answer = answer[: found.start()].rstrip(" *\n")
    result = Result(text=answer)
    providers = config.available_providers()

    photos = ctx.f("character_photo") + ctx.character_media
    if mode == "replace" and photos and (providers["gemini"] or providers["openai"]):
        try:
            frame = await media.extract_frame(ctx.f("video")[0])
            instruction = (
                "Replace the main person in the first image with the person shown in the other reference image(s). "
                "Keep exactly the same pose, framing, camera angle, background and lighting. Photorealistic, seamless."
                + (f" New character details: {ctx.v('new_character')}" if ctx.v("new_character") else "")
            )
            result.images = (await images.generate_image(image_engine(), instruction, [frame, *photos[:3]], "auto"))[:1]
            result.text += "\n\n## Первый кадр с новым персонажем\nНиже — готовый стартовый кадр. Его можно сразу оживить в видео."
            result.followups.append({
                "label": "Оживить кадр в видео", "tool": "video_gen",
                "values": {"prompt": anim, "enhance": "0" if anim else "1"}, "files": {"image": {"image": 0}},
            })
        except Exception as e:
            log.warning("character swap failed: %s", e)
            result.text += f"\n\n⚠️ Не удалось заменить персонажа на первом кадре: {e}"

    if mode == "replace" and providers["gemini"]:
        who = ctx.v("new_character") or "the person from the reference photo"
        result.followups.insert(0, {
            "label": "Заменить персонажа во всём видео (Omni)", "tool": "video_edit",
            "values": {"mode": "edit", "instruction": f"Replace the main character with {who}. "
                                                      "Keep the same movements, timing, camera, background and voice."},
            "files": {"source": {"from_field": "video"}, "refs": {"from_field": "character_photo"}},
        })

    if mode in ("translate", "full") and providers["elevenlabs"]:
        result.followups.append({
            "label": "Сделать дубляж (ElevenLabs)", "tool": "voices",
            "values": {"mode": "dub", "target_lang": LANG_CODES.get(ctx.v("target_lang"), "en")},
            "files": {"source": {"from_field": "video"}},
        })
    return result


IMAGE_GUIDE_GEMINI = (
    "Формат для Nano Banana (гайд Google): пиши связным описанием, как бриф художнику, а не списком "
    "ключевых слов — сюжет, объект, композиция, действие, место, стиль, свет, камера. Для узнаваемого героя "
    "перечисли неизменные черты (лицо, причёска, цвета одежды, пропорции). Текст на картинке — в кавычках."
)
IMAGE_GUIDE_OPENAI = (
    "Формат для GPT Image 2.5 (гайд OpenAI): начни с того, что это за изображение и в каком формате; затем "
    "блоки Scene (место, время, окружение) → Subject (кто/что) → Details (композиция, свет, материалы, стиль) → "
    "Constraints (что не должно меняться или появляться). Точный текст на картинке — в двойных кавычках."
)


async def run_image(tool: Tool, ctx: RunContext) -> Result:
    prompt, refs = ctx.v("prompt"), (ctx.f("refs") + ctx.character_media)[:4]
    if ctx.character:
        prompt += f"\n\nCharacter (keep appearance exactly): {ctx.character}"
    note = ""
    engine = image_engine(ctx.v("engine"))
    if ctx.flag("enhance"):
        guide = IMAGE_GUIDE_OPENAI if images.provider_of(engine) == "openai" else IMAGE_GUIDE_GEMINI
        system = (
            "Ты — эксперт по промптам для генерации изображений. Перепиши запрос пользователя в один промпт "
            f"на английском.\n{guide}\n"
            + (f"Референсов приложено: {len(refs)} — назови роль каждого (Image 1, Image 2…).\n" if refs else "")
            + "Если это постер/открытка/обложка со свободным местом под текст или логотип — опиши это место как "
              "пустой фон самой сцены (например, «the upper part is plain soft cream background»), без рамок, "
              "размеров и процентов. Надписи — только те, что дал пользователь, дословно в кавычках.\n"
            + prompt_rules.HYGIENE_RULE + "\n"
            + "Верни ТОЛЬКО сам промпт, без пояснений и кавычек вокруг него."
        )
        prompt = prompt_rules.sanitize(await llm.generate_text(ctx.provider, system, prompt, refs))
        note = f"**Улучшенный промпт:**\n```prompt\n{prompt}\n```"
    tasks = [images.generate_image(engine, prompt, refs, ctx.v("size", "1024x1536"), ctx.v("quality", "auto"))
             for _ in range(int(ctx.v("count", "1")))]
    imgs, failed = await gather_images(tasks)
    if failed:
        note += f"\n\n⚠️ Не удалось сгенерировать {failed} из {len(tasks)}."
    result = Result(text=note.strip(), images=imgs)
    for i in range(len(imgs)):
        result.followups.append({
            "label": f"Оживить вариант {i + 1}" if len(imgs) > 1 else "Оживить в видео",
            "tool": "video_gen", "values": {"enhance": "1"}, "files": {"image": {"image": i}},
        })
    return result


async def run_motion(tool: Tool, ctx: RunContext) -> Result:
    files = ctx.f("media")
    if not files and not ctx.v("script"):
        raise AIError("Загрузите видео/аудио или вставьте текст сценария.")
    if not files or not config.available_providers()["elevenlabs"]:
        return await run_text(tool, ctx)  # без ElevenLabs: Gemini сам посмотрит видео

    # Точная пословная расшифровка (ElevenLabs Scribe v2) → план по реальным таймкодам
    source = files[0]
    transcript = await voice.transcribe(source)
    phrases = subtitles.phrases_from_words(transcript.get("words", []))
    if not phrases:
        raise AIError("В файле не найдена речь.")
    srt = subtitles.to_srt(phrases)
    system = f"{PRODUCER}\n\n{tool.system}\n\n{lang_rule(ctx.lang)}"
    prompt = build_prompt(
        tool, ctx,
        "Сделай план моушн-дизайна по готовой расшифровке с точными таймкодами (секунды). Для каждой фразы: "
        "таймкод, ключевое слово-акцент, анимация (kinetic type, pop-up иконка, счётчик, подчёркивание, стрелки, "
        "B-roll), элементы на экране, переход, звук (SFX). Затем: общий стиль для монтажёра (шрифты, палитра в HEX, "
        "отступы, скорость — только в описательной части), "
        "как собрать в CapCut и After Effects, промпты для AI-генерации анимированных вставок.",
        f"Расшифровка (язык: {transcript.get('language_code', '?')}):\n{subtitles.timeline(phrases)}",
    )
    plan = await ask(ctx, system, prompt)
    result = Result(text=f"{plan}\n\n## Субтитры (SRT)\n```srt\n{srt}```")
    if source.is_video and ctx.flag("render"):
        width, height = await media.probe_size(source)
        ass = subtitles.to_ass(phrases, width, height, ctx.v("style", "Kinetic typography"))
        result.video = await media.burn_subtitles(source, ass)
        result.text = "✅ Видео с анимированными субтитрами — выше. Ниже — план моушн-дизайна для монтажа.\n\n" + result.text
    return result


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
        '"why": "зачем этот ракурс в монтаже", "image_prompt": "English edit instruction for the reference '
        'frame: the new camera position, shot size, lens and what must stay identical", "video_prompt": '
        '"English Veo 3.1 image-to-video prompt: only camera and subject motion over 8 seconds plus one '
        'SFX: line and one Ambient noise: line; do not re-describe the frame"}]}\n'
        f"Поля scene, name и why пиши на {lang} языке.\n" + prompt_rules.HYGIENE_RULE
    )
    data = extract_json(await llm.generate_text(ctx.provider, system, prompt, frame))
    angles = data.get("angles", [])[:count]

    md = [f"## Исходный кадр\n{data.get('scene', '')}"]
    for i, a in enumerate(angles, 1):
        md.append(
            f"## {i}. {a.get('name', '')}\n{a.get('why', '')}\n\n**Промпт кадра:**\n```\n{a.get('image_prompt', '')}\n```"
            f"\n**Промпт для анимации:**\n```\n{a.get('video_prompt', '')}\n```"
        )

    result = Result()
    if ctx.flag("generate") and angles:
        engine = image_engine()
        size = {"9:16": "1024x1536", "16:9": "1536x1024"}.get(ctx.v("aspect"), "1024x1024")
        outcomes = await asyncio.gather(*[
            images.generate_image(
                engine,
                "Using the reference image, show the exact same scene, characters, clothing, environment, "
                f"lighting and style from a different camera angle: {a.get('image_prompt', '')}",
                frame, size,
            )
            for a in angles
        ], return_exceptions=True)
        errors = [o for o in outcomes if isinstance(o, BaseException)]
        for a, out in zip(angles, outcomes):
            if isinstance(out, BaseException) or not out:
                continue
            result.images.append(out[0])
            result.followups.append({
                "label": f"Оживить: {a.get('name', 'ракурс')}", "tool": "video_gen",
                "values": {"prompt": a.get("video_prompt", ""), "enhance": "0",
                           "aspect": "16:9" if ctx.v("aspect") == "16:9" else "9:16"},
                "files": {"image": {"image": len(result.images) - 1}},
            })
        if errors:
            log.warning("angle images failed: %r", errors[0])
            md.append(f"⚠️ Не удалось сгенерировать {len(errors)} из {len(angles)} изображений: {errors[0]}")
    result.text = "\n\n".join(md)
    return result


async def run_voices(tool: Tool, ctx: RunContext) -> Result:
    mode = ctx.v("mode", "tts")
    if mode == "tts":
        if not ctx.v("text"):
            raise AIError("Введите текст для озвучки.")
        fast = ctx.v("tts_model") == "turbo"
        return Result(audio=await voice.text_to_speech(ctx.v("voice"), ctx.v("text"), fast))

    if mode == "sts":
        src = ctx.f("source")
        if not src:
            raise AIError("Загрузите аудио или видео с речью.")
        audio = await media.to_audio(src[0])
        new_audio = await voice.speech_to_speech(ctx.v("voice"), audio, ctx.flag("denoise"))
        if src[0].is_video and ctx.flag("keep_video"):
            return Result(video=await media.replace_audio(src[0], new_audio), audio=new_audio)
        return Result(audio=new_audio)

    if mode == "dub":
        src = ctx.f("source")
        if not src:
            raise AIError("Загрузите видео или аудио для дубляжа.")
        track = await voice.dub(src[0], ctx.v("target_lang", "en"))  # FLAC без потерь
        lang = dict(DUB_LANGS).get(ctx.v("target_lang"), ctx.v("target_lang"))
        note = f"✅ Дубляж (Dubbing v2) на язык: **{lang}**. Голоса спикеров и фоновая музыка сохранены."
        if src[0].is_video:
            return Result(text=note, video=await media.replace_audio(src[0], track))
        return Result(text=note, audio=await media.to_mp3(track))

    if mode == "stt":
        src = ctx.f("source")
        if not src:
            raise AIError("Загрузите аудио или видео с речью.")
        data = await voice.transcribe(src[0])
        phrases = subtitles.phrases_from_words(data.get("words", []), max_words=8)
        speakers = {w.get("speaker_id") for w in data.get("words", []) if w.get("speaker_id")}
        text = f"**Язык:** {data.get('language_code', '?')} · **спикеров:** {len(speakers) or 1}\n\n"
        text += f"## Текст\n{data.get('text', '').strip()}\n\n## Субтитры (SRT)\n```srt\n{subtitles.to_srt(phrases)}```"
        return Result(text=text)

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
        "## Неизменные черты — короткий список: форма лица, глаза, причёска, цвета и детали одежды, пропорции\n"
        "## Промпт персонажа — 60–90 слов на английском в блоке ```prompt, который можно вставлять в каждый "
        "промпт для узнаваемости (описание связным текстом, без списка ключевых слов)\n"
        "## Negative prompt — чего избегать (```text)\n"
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
    result = Result(text=prompt_rules.sanitize_answer(results[0]))
    ctx.refine = {"system": system, "prompt": prompt, "provider": ctx.provider}
    found = re.search(r"Промпт персонажа[^\n]*\n+(?:[^`]*?)```[^\n]*\n(.*?)```", result.text, re.S)
    result.character = {"name": ctx.v("name"), "prompt": found.group(1).strip() if found else ""}
    if len(results) > 1:
        if isinstance(results[1], BaseException):
            log.warning("character sheet failed: %s", results[1])
            result.text += f"\n\n⚠️ Не удалось нарисовать карточку: {results[1]}"
        else:
            result.images = results[1]
    return result


VIDEO_ENHANCE = (
    "Ты — режиссёр AI-видео. Перепиши запрос пользователя в один готовый промпт для {engine}, "
    "формат {aspect}.\n{rules}\n"
    "Реплики героев оставь на языке пользователя, в кавычках.\n{hygiene}\n"
    "Верни ТОЛЬКО сам промпт, без пояснений и без блоков кода."
)


ENGINE_NAMES = {"veo": "Veo 3.1", "veo_fast": "Veo 3.1 Fast", "omni": "Gemini Omni Flash 1.1"}


async def run_video_gen(tool: Tool, ctx: RunContext) -> Result:
    llm.require("gemini")
    engine = ctx.v("engine", "veo")
    image = (ctx.f("image") or [None])[0]
    seconds = int(ctx.v("seconds", "8"))
    aspect = ctx.v("aspect", "9:16")
    resolution = ctx.v("resolution", "1080p")
    prompt = ctx.v("prompt") or "Bring this frame to life with natural, cinematic motion."
    if ctx.character:
        prompt += f"\n\nMain character (keep appearance exactly): {ctx.character}"
    if engine == "omni":
        prompt += f"\n\nTarget length: about {seconds} seconds."
    if ctx.flag("enhance"):
        generator = "omni" if engine == "omni" else "veo"
        seconds = prompt_rules.clamp_seconds(generator, seconds)
        system = VIDEO_ENHANCE.format(engine=ENGINE_NAMES.get(engine, "Veo"), aspect=aspect,
                                      rules=prompt_rules.rules_for(generator, seconds),
                                      hygiene=prompt_rules.HYGIENE_RULE)
        refs = ([image] if image else []) + ctx.character_media[:2]
        prompt = (await llm.generate_text(ctx.provider, system, prompt, refs)).strip().strip("`")
        issues = prompt_rules.check_prompt(prompt, generator, seconds)
        if issues:
            prompt = (await llm.generate_text(
                ctx.provider, system,
                "Исправь промпт, нарушения: " + "; ".join(issues) + ". Верни только исправленный промпт.\n\n" + prompt,
            )).strip().strip("`")
    prompt = prompt_rules.sanitize(prompt)
    clip = await video.generate_video(engine, prompt, image, ctx.character_media, aspect, seconds, resolution)
    result = Result(text=f"**{ENGINE_NAMES.get(engine, engine)} · {resolution}**\n\n**Промпт:**\n```prompt\n{prompt}\n```", video=clip)
    result.followups.append({"label": "Продлить это видео (Omni)", "tool": "video_edit",
                             "values": {"mode": "extend"}, "files": {"source": {"video": True}}})
    return result


OMNI_EDIT_GUIDE = {
    "edit": (
        "Перепиши просьбу пользователя в промпт редактирования видео для Gemini Omni Flash (на английском). "
        "Гайд: правка — это «дельта», а не описание сцены. 2–3 предложения: глагол изменения (Replace / Change / "
        "Add / Remove / Restyle), уточнение, и обязательная фраза-фиксатор: что сохранить (движения, тайминг, "
        "камера, фон, голос) и «Keep everything else identical.». Если приложены референсы — сошлись на них как "
        "«the person/object in the reference image». Цвета — словами, без HEX, процентов и отступов. "
        "Верни только промпт."
    ),
    "extend": (
        "Перепиши просьбу в промпт продления видео для Gemini Omni Flash (на английском): что происходит дальше "
        "(1–2 предложения) и фиксатор «Continue seamlessly from the last frame with the same characters, location, "
        "lighting and camera style.». Верни только промпт."
    ),
}

async def run_video_edit(tool: Tool, ctx: RunContext) -> Result:
    llm.require("gemini")
    src = ctx.f("source")
    if not src or not src[0].is_video:
        raise AIError("Загрузите видео.")
    mode = ctx.v("mode", "edit")
    refs = (ctx.f("refs") + ctx.character_media)[:3]
    instruction = ctx.v("instruction")
    if mode == "edit" and not instruction:
        raise AIError("Опишите, что изменить в видео.")
    request = instruction or "continue the action naturally"
    if ctx.character:
        request += f"\nCharacter description: {ctx.character}"
    if refs:
        request += f"\n({len(refs)} reference image(s) attached for the new character/object.)"
    providers = config.available_providers()
    llm_provider = next((p for p in (ctx.provider, "gemini", "claude", "openai") if providers.get(p)), "gemini")
    prompt = (await llm.generate_text(llm_provider, OMNI_EDIT_GUIDE[mode], request)).strip().strip("`")
    clip = await video.edit_video(src[0], prompt, refs, mode, ctx.v("resolution", "1080p"), ctx.v("aspect", "9:16"))
    label = "Видео отредактировано" if mode == "edit" else "Видео продлено"
    return Result(text=f"✅ {label} в Gemini Omni Flash 1.1.", video=clip)


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
            select("target", "Промпты сцен под генератор", prompt_rules.TARGET_OPTIONS,
                   show_if={"mode": ["full", "replace"]}),
            select("target_lang", "Язык перевода", OUT_LANGS),
            area("new_character", "Новый персонаж", "Опишите, на кого заменить (необязательно)"),
            files("character_photo", "Фото нового персонажа", "image/*"),
        ],
        run=run_video_study, uses_llm=False, needs=("gemini",), character=True,
        hint="Видео анализирует Gemini (ролики до 2–3 минут). В режиме «Замена персонажа» с фото "
             "получите готовый первый кадр с новым героем — его можно сразу оживить в видео.",
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
        "seedance", "Seedance 2.5 промпт", "Режиссёрский промпт по официальной структуре", "zap", "prompts",
        [
            area("idea", "Идея сцены", "Что должно происходить в видео, реплики героев", True),
            select("duration", "Длительность", [("4", "4 с"), ("6", "6 с"), ("8", "8 с"), ("10", "10 с"),
                                                 ("12", "12 с"), ("15", "15 с"), ("20", "20 с"),
                                                 ("25", "25 с"), ("30", "30 с")], "10"),
            select("aspect", "Формат", [("9:16", "9:16"), ("16:9", "16:9"), ("1:1", "1:1"), ("4:3", "4:3"),
                                        ("3:4", "3:4"), ("21:9", "21:9")]),
            text("style", "Стиль", "Например: кинематографичный, аниме, реклама, документальный"),
            files("ref", "Референсы (герой, продукт, локация)", "image/*", multiple=True, max_files=9),
        ],
        system="Ты пишешь промпты уровня профессионального режиссёра и оператора для Seedance 2.5 (ByteDance).",
        task=(
            "Напиши промпт для Seedance 2.5 под длительность {duration} с и формат {aspect}.\n"
            "1. Коротко (на языке ответа): замысел и раскадровка по отрезкам — что в кадре, крупность, "
            "движение камеры, звук.\n2. **Финальный промпт** — один блок ```prompt строго по формату Seedance 2.5.\n"
            "3. Две альтернативы (более динамичная и более атмосферная) — тоже полноценные промпты ```prompt "
            "той же длительности.\nЕсли приложены референсы — пронумеруй их @Image1, @Image2… в порядке "
            "приложения и привяжи к ролям."
        ),
        character=True, generator="seedance", seconds_field="duration",
        hint="Промпт пишется по официальной структуре Seedance 2.5 и проверяется автоматически: "
             "таймлайн, длительность, привязка референсов.",
    ),
    Tool(
        "minidrama", "Мини-драма", "Вертикальный сериал из 5 серий", "clapper", "scripts",
        [
            area("premise", "Завязка", "О чём сериал, кто герои", True),
            select("genre", "Жанр", ["Романтика", "Семейная драма", "Месть", "Триллер", "Комедия",
                                     "Мистика", "Бизнес / успех"]),
            select("length", "Длина серии", ["30 секунд", "60 секунд", "90 секунд"], "60 секунд"),
            text("dialog_lang", "Язык диалогов", "Например: узбекский"),
            select("target", "Промпты под генератор", prompt_rules.TARGET_OPTIONS),
            select("scene_len", "Длина одной сцены", [("8", "8 с"), ("10", "10 с"), ("15", "15 с")], "8"),
        ],
        system="Ты — шоураннер вертикальных мини-сериалов, которые смотрят запоем.",
        task=(
            "Создай вертикальный мини-сериал из 5 серий.\n"
            "Сначала: название, логлайн, персонажи — для каждого подробная внешность и одежда "
            "(одинаковое описание будем использовать во всех промптах) и промпт для character sheet.\n"
            "Для каждой серии: название, сцены с таймкодами, диалоги, клиффхэнгер в конце и "
            "промпт ```prompt для выбранного генератора на каждую сцену (длительность сцены — {scene_len} с, "
            "но не больше лимита генератора) с дословно одинаковыми описаниями персонажей."
        ),
        character=True, seconds_field="scene_len",
    ),
    Tool(
        "serial", "Создание сериала", "Связанные сцены под Veo, Seedance, Kling, Grok", "layers", "prompts",
        [
            area("story", "История", "Перескажите сюжет целиком", True),
            number("scenes", "Количество сцен", 6, 2, 20),
            select("target", "Промпты под генератор", prompt_rules.TARGET_OPTIONS),
            select("scene_len", "Длина одной сцены", [("8", "8 с"), ("10", "10 с"), ("15", "15 с")], "8"),
            area("character", "Персонажи", "Внешность героев (необязательно — придумаем)"),
            text("style", "Визуальный стиль", "Например: кино 35мм, Pixar 3D, аниме"),
            files("ref", "Референс персонажа", "image/*"),
        ],
        system="Ты отвечаешь за непрерывность (continuity) AI-сериала: персонажи и мир не должны «плыть».",
        task=(
            "Разбей историю на {scenes} связанных сцен по {scene_len} с (не больше лимита выбранного генератора).\n"
            "Начни с блоков **Character bible** и **Style bible** (на английском, в ```text; цвета — словами, "
            "без HEX-кодов и технических параметров, потому что эти блоки копируются в каждый промпт).\n"
            "Для каждой сцены: описание, промпт ```prompt (дословно повторяй блок персонажа и стиля в "
            "каждом промпте), **последний кадр** — его можно использовать как стартовый кадр следующей "
            "сцены, и реплика/закадровый текст. Каждая сцена продолжает предыдущую без скачков."
        ),
        character=True, seconds_field="scene_len",
    ),
    Tool(
        "grok", "Промпты для Grok", "Кадры, как в кино", "aperture", "prompts",
        [
            area("idea", "Идея", "Что должно быть в кадрах", True),
            select("genre", "Жанр", ["Драма", "Боевик", "Нуар", "Фантастика", "Хоррор", "Романтика",
                                     "Исторический", "Реклама"]),
            number("count", "Сколько кадров", 6, 1, 20),
            select("seconds", "Длина анимации", [("6", "6 с"), ("10", "10 с"), ("15", "15 с")], "10"),
        ],
        system="Ты — оператор-постановщик голливудского уровня и знаешь, как писать промпты для Grok Imagine.",
        task=(
            "Напиши {count} промптов для Grok Imagine, чтобы кадры выглядели как из большого кино. "
            "Для каждого: название кадра, **промпт изображения** ```prompt (subject, action, environment, "
            "style, camera & lighting — например 35mm / anamorphic, color grade, film stock, mood) и "
            "**промпт анимации** ```prompt — короткий (1–2 предложения), только движение камеры и героя "
            "и конкретный звук, на {seconds} с."
        ),
        character=True, generator="grok", seconds_field="seconds",
    ),
    Tool(
        "image", "Изображения", "GPT Image 2.5 и Nano Banana", "image", "visual",
        [
            area("prompt", "Что нарисовать", "Опишите изображение", True),
            files("refs", "Референсы", "image/*", multiple=True, max_files=4),
            select("engine", "Генератор", [("nb2", "Nano Banana 2 — быстро"), ("nbpro", "Nano Banana Pro — качество"),
                                           ("flare", "GPT Image 2.5 Flare — быстро"),
                                           ("sunburst", "GPT Image 2.5 Sunburst — качество")]),
            select("size", "Формат и разрешение", [
                ("1024x1536", "Вертикальный 2:3 · 1K"), ("1152x2048", "Вертикальный 9:16 · 2K"),
                ("2160x3840", "Вертикальный 9:16 · 4K"), ("1024x1024", "Квадрат · 1K"), ("2048x2048", "Квадрат · 2K"),
                ("1536x1024", "Горизонтальный 3:2 · 1K"), ("2048x1152", "Горизонтальный 16:9 · 2K"),
                ("3840x2160", "Горизонтальный 16:9 · 4K")]),
            select("quality", "Качество (для GPT Image)", [("auto", "Авто"), ("high", "Высокое"), ("max", "Максимум")]),
            select("count", "Вариантов", ["1", "2", "3", "4"]),
            check("enhance", "Улучшить промпт с помощью ИИ", True),
        ],
        run=run_image, character=True,
        hint="Nano Banana работает по ключу Gemini, GPT Image — по ключу OpenAI. 4K и «Максимум» дороже и дольше.",
    ),
    Tool(
        "motion", "Видео-анимация", "Моушн-дизайн под каждую фразу", "sparkles", "visual",
        [
            files("media", "Видео или аудио с речью", "video/*,audio/*"),
            area("script", "…или текст сценария", "Если нет видео — вставьте текст"),
            select("style", "Стиль", ["Kinetic typography", "Минимализм", "Яркий поп", "Неон / техно",
                                      "Корпоративный", "Документальный"]),
            check("render", "Вшить анимированные субтитры в видео", True),
            select("aspect", "Формат", ASPECTS),
        ],
        system="Ты — моушн-дизайнер, который делает анимации для говорящих голов и экспертных роликов.",
        task=(
            "Сделай план моушн-дизайна. Если приложено видео или аудио — расшифруй речь и разбей на фразы "
            "с точными таймкодами. Для каждой фразы: таймкод, текст, ключевое слово-акцент, анимация "
            "(kinetic type, pop-up иконка, счётчик, подчёркивание, стрелки, B-roll и т.д.), элементы на экране, "
            "переход, звук (SFX).\nЗатем: общий стиль для монтажёра (шрифты, палитра в HEX, отступы, скорость анимаций "
            "— только в описательной части, не в промптах), как собрать в "
            "CapCut и в After Effects, промпты для AI-генерации анимированных вставок. "
            "В конце — субтитры в формате SRT в блоке кода."
        ),
        run=run_motion,
        hint="Видео расшифровывается ElevenLabs Scribe v2 с точностью до слова, и в него вшиваются "
             "анимированные субтитры в выбранном стиле. Без ключа ElevenLabs видео анализирует Gemini.",
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
        "video_gen", "Генерация видео", "Veo 3.1 и Gemini Omni: текст или кадр", "film", "media",
        [
            area("prompt", "Что происходит в видео", "Действие, камера, настроение, реплики. Можно по-русски"),
            files("image", "Первый кадр", "image/*"),
            select("engine", "Генератор", [("veo", "Veo 3.1"), ("veo_fast", "Veo Fast"), ("omni", "Omni")]),
            select("aspect", "Формат", [("9:16", "9:16"), ("16:9", "16:9")]),
            select("seconds", "Длительность", [("4", "4 с"), ("6", "6 с"), ("8", "8 с")], "8"),
            select("resolution", "Разрешение", [("720p", "720p"), ("1080p", "1080p"), ("4k", "4K")], "1080p"),
            check("enhance", "Улучшить промпт с помощью ИИ", True),
        ],
        run=run_video_gen, character=True, needs=("gemini",),
        hint="Всё работает по ключу Gemini (Sora API OpenAI закрыл в сентябре 2026). Veo 3.1 — лучшее качество "
             "со звуком, Fast — дешевле, Omni — новая модель Google. Генерация 1–5 минут, оплата за секунду видео.",
    ),
    Tool(
        "video_edit", "Редактор видео", "Замена героя, фона, стиля; продление", "wand", "media",
        [
            files("source", "Видео", "video/*", required=True),
            select("mode", "Что сделать", [("edit", "Изменить"), ("extend", "Продлить")]),
            area("instruction", "Что изменить", "Например: замени героя на девушку с фото, сделай вечер, "
                 "добавь снег. Можно по-русски"),
            files("refs", "Референсы (новый герой, предмет)", "image/*", multiple=True, max_files=3,
                  show_if={"mode": ["edit"]}),
            select("aspect", "Формат", [("9:16", "9:16"), ("16:9", "16:9")], show_if={"mode": ["extend"]}),
            select("resolution", "Разрешение", [("720p", "720p"), ("1080p", "1080p"), ("4k", "4K")], "1080p"),
        ],
        run=run_video_edit, uses_llm=False, needs=("gemini",), character=True,
        hint="Gemini Omni Flash 1.1 меняет готовое видео по описанию: героя, одежду, фон, время суток, стиль — "
             "сохраняя движения и камеру. «Продлить» добавляет до 10 секунд продолжения.",
    ),
    Tool(
        "voices", "Голоса", "Озвучка, клон и замена голоса", "mic", "media",
        [
            select("mode", "Режим", [("tts", "Озвучить текст"), ("dub", "Дубляж видео на другой язык"),
                                     ("sts", "Заменить голос в аудио/видео"), ("clone", "Клонировать голос"),
                                     ("stt", "Расшифровать речь в текст и субтитры")]),
            select("tts_model", "Модель", [("v4", "Eleven v4"), ("turbo", "v4 Turbo")], show_if={"mode": ["tts"]}),
            {"name": "voice", "label": "Голос", "type": "voice", "required": True,
             "show_if": {"mode": ["tts", "sts"]}},
            area("text", "Текст", "Текст для озвучки. Эмоции — тегами: [laughs] [whispers] [excited] [sighs]",
                 show_if={"mode": ["tts"]}),
            files("source", "Аудио или видео с речью", "audio/*,video/*", show_if={"mode": ["sts", "dub", "stt"]}),
            select("target_lang", "Язык дубляжа", DUB_LANGS, show_if={"mode": ["dub"]}),
            check("keep_video", "Вернуть видео с новым голосом", True, show_if={"mode": ["sts"]}),
            text("name", "Название голоса", "Например: Мой голос", show_if={"mode": ["clone"]}),
            files("samples", "Образцы голоса", "audio/*,video/*", multiple=True, max_files=5,
                  show_if={"mode": ["clone"]}),
            area("preview", "Тестовая фраза", "Озвучим ей новый голос (необязательно)",
                 show_if={"mode": ["clone"]}),
            check("denoise", "Убрать фоновый шум", False, show_if={"mode": ["sts", "clone"]}),
        ],
        run=run_voices, uses_llm=False, needs=("elevenlabs",),
        hint="ElevenLabs: озвучка Eleven v4 (90+ языков, включая узбекский), дубляж Dubbing v2 голосами самих "
             "спикеров с сохранением музыки, расшифровка Scribe v2. Для клона хватит 10 секунд чистой речи.",
    ),
    Tool(
        "character", "Карточка персонажа", "Карточка из 3 фото", "user", "visual",
        [
            files("photos", "Фото персонажа (до 3)", "image/*", required=True, multiple=True, max_files=3),
            text("name", "Имя персонажа", "Необязательно"),
            area("notes", "Дополнительно", "Роль, характер, во что одеть"),
            check("sheet", "Нарисовать character sheet", True),
            select("engine", "Генератор картинки", [("nbpro", "Nano Banana Pro"), ("nb2", "Nano Banana 2"),
                                                    ("sunburst", "GPT Image 2.5 Sunburst")]),
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
