"""Точка входа: запускает Telegram-бота (long polling) и веб-сервер Mini App."""

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message, WebAppInfo,
)
from aiohttp import web

from . import auth, config
from .web import create_app

log = logging.getLogger(__name__)
router = Router()

WELCOME = (
    "Помощник для AI-видео контента.\n\n"
    "Здесь есть всё, что нужно:\n"
    "🎬 Профессиональные промпты для видео\n"
    "✨ Моушн-дизайн анимация для видео\n"
    "🎥 Новые ракурсы камеры из одного дубля\n"
    "🎙 Клонирование и замена голоса\n"
    "🎭 Карточки персонажей\n\n"
    "Нажмите кнопку ниже, чтобы начать."
)


def open_app_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Открыть", web_app=WebAppInfo(url=config.WEBAPP_URL)),
    ]])


@router.message()
async def on_message(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not auth.is_allowed(user_id):
        await message.answer(
            "⛔ Это личный бот.\n\n"
            f"Ваш Telegram ID: <code>{user_id}</code>\n"
            "Если это ваш бот — добавьте этот ID в переменную ALLOWED_USER_IDS и перезапустите его.",
            parse_mode="HTML",
        )
        return
    if not config.WEBAPP_URL.startswith("https://"):
        await message.answer("⚠️ Не задан WEBAPP_URL (публичный https-адрес приложения). См. README.")
        return
    await message.answer(WELCOME, reply_markup=open_app_keyboard())


async def setup_menu_button(bot: Bot) -> None:
    if not config.WEBAPP_URL.startswith("https://"):
        log.warning("WEBAPP_URL не задан или не https — кнопка Mini App не будет работать")
        return
    try:
        for uid in config.ALLOWED_USER_IDS:
            await bot.set_chat_menu_button(
                chat_id=uid, menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=config.WEBAPP_URL)),
            )
    except Exception as e:  # пользователь ещё не писал боту — не страшно
        log.info("menu button not set: %s", e)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN (см. .env.example)")
    if not config.ALLOWED_USER_IDS:
        log.warning("ALLOWED_USER_IDS пуст — никто не сможет пользоваться ботом. Напишите боту /start, чтобы узнать свой ID.")
    if config.DEV_SKIP_AUTH:
        log.warning("DEV_SKIP_AUTH=1 — проверка доступа ОТКЛЮЧЕНА. Не используйте это на сервере!")

    bot = Bot(config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    runner = web.AppRunner(create_app(bot))
    await runner.setup()
    await web.TCPSite(runner, config.HOST, config.PORT).start()
    log.info("Mini App: http://%s:%s  (публичный адрес: %s)", config.HOST, config.PORT, config.WEBAPP_URL or "не задан")

    await setup_menu_button(bot)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
