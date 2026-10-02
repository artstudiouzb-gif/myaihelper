"""HTTP-сервер: отдаёт Mini App и API для него."""

import asyncio
import logging
import mimetypes
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputMediaPhoto
from aiohttp import web

from . import auth, config
from .ai import voice
from .ai.llm import AIError, Media
from .tools import TOOLS, TOOLS_BY_ID, Result, RunContext, refine, run_tool

log = logging.getLogger(__name__)

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
MEDIA_TTL = 3 * 3600
TG_UPLOAD_LIMIT = 49 * 1024 * 1024

# Временное хранилище результатов (картинки, аудио, видео), чтобы показать их в Mini App
_media: dict[str, tuple[float, bytes, str]] = {}


def store_media(data: bytes, mime: str) -> str:
    now = time.time()
    for key in [k for k, (t, _, _) in _media.items() if now - t > MEDIA_TTL]:
        del _media[key]
    key = secrets.token_urlsafe(24)
    _media[key] = (now, data, mime)
    return f"/media/{key}"


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    if config.DEV_SKIP_AUTH:
        uid = next(iter(config.ALLOWED_USER_IDS), 0)
        request["user"] = {"id": uid, "first_name": "Dev"}
        return await handler(request)
    user = auth.validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), config.BOT_TOKEN)
    if not user:
        return web.json_response({"error": "Откройте приложение через Telegram-бота."}, status=401)
    if not auth.is_allowed(user.get("id")):
        return web.json_response({"error": f"Доступ запрещён. Ваш ID: {user.get('id')}"}, status=403)
    request["user"] = user
    return await handler(request)


async def index(_: web.Request) -> web.Response:
    return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})


async def api_config(request: web.Request) -> web.Response:
    return web.json_response({
        "user": {k: request["user"].get(k, "") for k in ("first_name", "last_name", "photo_url")},
        "providers": config.available_providers(),
        "models": {
            "claude": config.CLAUDE_MODEL, "openai": config.OPENAI_MODEL, "gemini": config.GEMINI_MODEL,
            "elevenlabs": config.ELEVENLABS_TTS_MODEL,
        },
        "stack": [
            ["Текст", f"{config.CLAUDE_MODEL} · {config.OPENAI_MODEL} · {config.GEMINI_MODEL}"],
            ["Изображения", f"{config.GEMINI_IMAGE_MODEL} · {config.GEMINI_IMAGE_MODEL_PRO} · "
                            f"{config.OPENAI_IMAGE_MODEL} · {config.OPENAI_IMAGE_MODEL_HQ}"],
            ["Видео", f"{config.VEO_MODEL} · {config.VEO_FAST_MODEL} · {config.OMNI_MODEL}"],
            ["Голос", f"{config.ELEVENLABS_TTS_MODEL} · {config.ELEVENLABS_DUBBING_MODEL} · "
                      f"{config.ELEVENLABS_STT_MODEL} · {config.ELEVENLABS_STS_MODEL}"],
        ],
        "tools": [t.public() for t in TOOLS],
    })


async def api_voices(_: web.Request) -> web.Response:
    try:
        return web.json_response({"voices": await voice.list_voices()})
    except AIError as e:
        return web.json_response({"error": str(e)}, status=400)


def _mime(field: web.FileField) -> str:
    mime = (field.content_type or "").lower()
    if not mime or mime == "application/octet-stream":
        mime = mimetypes.guess_type(field.filename or "")[0] or "application/octet-stream"
    return "image/jpeg" if mime == "image/jpg" else mime


@dataclass
class Job:
    """Фоновая генерация: Mini App опрашивает её статус, а готовый результат дублируется в чат."""
    id: str
    user_id: int
    title: str
    created: float = field(default_factory=time.time)
    status: str = "running"  # running | done | error
    result: dict | None = None
    error: str = ""
    refine: dict | None = None  # контекст для «Доработать»


_jobs: dict[str, Job] = {}
_tasks: set[asyncio.Task] = set()  # держим ссылки, чтобы задачи не собрал сборщик мусора


def serialize(result: Result, chat_note: str, refinable: bool) -> dict:
    images = [store_media(i, "image/png") for i in result.images]
    video_url = store_media(result.video, "video/mp4") if result.video else None
    followups = []
    for f in result.followups:
        files = {}
        for target, src in (f.get("files") or {}).items():
            if "image" in src and src["image"] < len(images):
                files[target] = {"url": images[src["image"]], "name": f"{target}.png"}
            elif src.get("video") and video_url:
                files[target] = {"url": video_url, "name": f"{target}.mp4"}
            elif "from_field" in src:
                files[target] = src
        followups.append({**f, "files": files})
    return {
        "text": result.text,
        "images": images,
        "audio": store_media(result.audio, "audio/mpeg") if result.audio else None,
        "video": video_url,
        "chat_note": chat_note,
        "followups": followups,
        "character": result.character,
        "refinable": refinable and bool(result.text),
    }


def start_job(app: web.Application, user_id: int, title: str, work, to_chat: bool,
              refine_ctx_getter=None) -> Job:
    now = time.time()
    for key in [k for k, j in _jobs.items() if now - j.created > MEDIA_TTL]:
        del _jobs[key]
    job = Job(id=secrets.token_urlsafe(12), user_id=user_id, title=title)
    _jobs[job.id] = job

    async def runner() -> None:
        started = time.monotonic()
        try:
            result: Result = await work()
            job.refine = refine_ctx_getter() if refine_ctx_getter else None
            note = await send_to_chat(app["bot"], user_id, title, result, to_chat)
            job.result = serialize(result, note, job.refine is not None)
            job.status = "done"
        except AIError as e:
            job.error, job.status = str(e), "error"
        except Exception as e:  # ошибки API провайдеров: нет баланса, неверный ключ и т.п.
            log.exception("job %s (%s) failed", job.id, title)
            job.error, job.status = f"{type(e).__name__}: {str(e)[:500]}", "error"
        elapsed = time.monotonic() - started
        log.info("job %s (%s) %s in %.1fs", job.id, title, job.status, elapsed)
        if job.status == "error" and elapsed > 30 and app["bot"] is not None:
            # пользователь мог уже закрыть приложение — сообщим об ошибке в чат
            try:
                await app["bot"].send_message(user_id, f"⚠️ {title}: {job.error}")
            except Exception as e:
                log.warning("cannot notify about error: %s", e)

    task = asyncio.create_task(runner())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


async def api_run(request: web.Request) -> web.Response:
    tool = TOOLS_BY_ID.get(request.match_info["tool_id"])
    if not tool:
        return web.json_response({"error": "Раздел не найден"}, status=404)

    form = await request.post()
    values: dict[str, str] = {}
    files: dict[str, list[Media]] = {}
    for name, value in form.items():
        if isinstance(value, web.FileField):
            data = value.file.read()
            if data:
                files.setdefault(name, []).append(Media(data, _mime(value), value.filename or name))
        else:
            values[name] = str(value)

    ctx = RunContext(
        values=values, files=files,
        provider=values.pop("_provider", "claude"), lang=values.pop("_lang", "ru"),
        character=values.pop("_character", "").strip(),
        character_media=files.pop("_character_photos", [])[:3],
    )
    to_chat = values.pop("_to_chat", "1") == "1"
    job = start_job(request.app, request["user"]["id"], tool.title, lambda: run_tool(tool, ctx), to_chat,
                    lambda: ctx.refine)
    return web.json_response({"job": job.id})


async def api_refine(request: web.Request) -> web.Response:
    data = await request.json()
    base = _jobs.get(data.get("job", ""))
    instruction = (data.get("instruction") or "").strip()
    if not instruction:
        return web.json_response({"error": "Напишите, что изменить."}, status=400)
    if not base or base.user_id != request["user"]["id"] or not base.refine:
        return web.json_response({"error": "Контекст устарел (сервер перезапускался или прошло больше 3 часов). "
                                           "Запустите генерацию заново."}, status=410)
    context = base.refine
    previous = data.get("text") or (base.result or {}).get("text", "")

    async def work() -> Result:
        return Result(text=await refine(context, previous, instruction))

    job = start_job(request.app, request["user"]["id"], base.title, work, data.get("to_chat", True),
                    lambda: context)
    return web.json_response({"job": job.id})


async def api_job(request: web.Request) -> web.Response:
    job = _jobs.get(request.match_info["job_id"])
    if not job or job.user_id != request["user"]["id"]:
        return web.json_response({"status": "missing", "error": "Задача не найдена (сервер перезапускался?)"},
                                 status=404)
    return web.json_response({
        "status": job.status, "result": job.result, "error": job.error,
        "elapsed": round(time.time() - job.created),
    })


def split_text(text: str, limit: int = 4000) -> list[str]:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks + ([text] if text else [])


async def send_text(bot: Bot, chat_id: int, title: str, text: str) -> None:
    for chunk in split_text(f"🔹 {title}\n\n{text}"):
        await bot.send_message(chat_id, chunk)


async def send_to_chat(bot: Bot | None, chat_id: int, title: str, result: Result, with_text: bool) -> str:
    """Дублирует результат в чат с ботом: медиа — всегда, текст — если включено."""
    if bot is None or not chat_id:
        return ""
    try:
        if with_text and result.text:
            await send_text(bot, chat_id, title, result.text)
        if len(result.images) == 1:
            await bot.send_document(chat_id, BufferedInputFile(result.images[0], "image.png"), caption=title)
        elif result.images:
            group = [InputMediaPhoto(media=BufferedInputFile(img, f"image{i}.png")) for i, img in enumerate(result.images[:10])]
            await bot.send_media_group(chat_id, group)
        if result.video:
            if len(result.video) > TG_UPLOAD_LIMIT:
                return "Видео больше 50 МБ — его можно скачать только из приложения."
            await bot.send_video(chat_id, BufferedInputFile(result.video, "video.mp4"), caption=title)
        elif result.audio:
            await bot.send_audio(chat_id, BufferedInputFile(result.audio, "voice.mp3"), caption=title)
    except Exception as e:
        log.warning("send to chat failed: %s", e)
        return "Не удалось отправить результат в чат."
    return ""


async def api_send(request: web.Request) -> web.Response:
    data = await request.json()
    await send_text(request.app["bot"], request["user"]["id"], data.get("title", "Результат"), data.get("text", ""))
    return web.json_response({"ok": True})


async def media(request: web.Request) -> web.Response:
    item = _media.get(request.match_info["key"])
    if not item:
        raise web.HTTPNotFound()
    _, data, mime = item
    return web.Response(body=data, content_type=mime, headers={"Cache-Control": "private, max-age=3600"})


async def health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


def create_app(bot: Bot | None) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=config.MAX_UPLOAD_MB * 1024 * 1024)
    app["bot"] = bot
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/media/{key}", media)
    app.router.add_get("/api/config", api_config)
    app.router.add_get("/api/voices", api_voices)
    app.router.add_post("/api/run/{tool_id}", api_run)
    app.router.add_post("/api/send", api_send)
    app.router.add_post("/api/refine", api_refine)
    app.router.add_get("/api/jobs/{job_id}", api_job)
    app.router.add_static("/static/", WEBAPP_DIR)
    return app
