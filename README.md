# myaihelper — личный AI-помощник для видео-контента

Telegram-бот с Mini App: 15 инструментов для создания AI-видео на ваших собственных ключах
**Claude, ChatGPT, Gemini и ElevenLabs**. Без подписок и баланса — платите только провайдерам по факту.

| Раздел | Что делает | Через что работает |
|---|---|---|
| 💡 Генератор идей | Вирусные идеи по теме | Claude / ChatGPT / Gemini (на выбор) |
| 🪝 Вирусные хуки | Хуки на первые 3 секунды | на выбор |
| 🔁 Разбор видео | Транскрипт, перевод, раскадровка; замена персонажа с готовым первым кадром | Gemini (понимает видео) |
| 📱 Stories и Reels | Контент-план, мини-сериалы в Stories | на выбор |
| ⚡ Seedance промпт | Режиссёрский промпт по шотам | на выбор |
| 🎬 Мини-драма | Вертикальный сериал из 5 серий | на выбор |
| 🎞️ Создание сериала | Связанные 10-секундные промпты с continuity | на выбор |
| 👑 Промпты для Grok | Кинематографичные кадры | на выбор |
| 🎨 Изображения | Картинка из текста или по референсам, до 4K | GPT Image 2.5 (Flare / Sunburst) или Nano Banana 2 / Pro |
| ✨ Видео-анимация | **Готовое видео с анимированными субтитрами** + план моушн-дизайна + SRT | ElevenLabs Scribe v2 + на выбор |
| 🎥 Ракурсы камеры | Новые ракурсы из одного кадра (промпты + картинки) | на выбор + Gemini/OpenAI для картинок |
| 🎬 Генерация видео | Видео из текста, кадра или референсов, до 4K, со звуком | Veo 3.1 / Veo 3.1 Fast / Gemini Omni Flash 1.1 |
| 🪄 Редактор видео | Замена героя, одежды, фона, стиля в готовом видео; продление ролика | Gemini Omni Flash 1.1 |
| 🎙️ Голоса | Озвучка Eleven v4 (теги эмоций), дубляж Dubbing v2 с сохранением фона, клон, замена голоса, расшифровка | ElevenLabs |
| 🎭 Карточка персонажа | Описание + character sheet по 3 фото | на выбор + Gemini/OpenAI |

Картинки, аудио и видео бот присылает и в чат. История результатов хранится на устройстве (вкладка «История»).

**Связки между разделами:**
- у каждого промпта в результате есть кнопка **«Видео»** — сразу генерирует ролик по нему;
- ракурсы, картинки и кадр с заменённым персонажем можно **«Оживить»** одной кнопкой;
- после перевода видео — кнопка **«Сделать дубляж»** с тем же роликом;
- **«Доработать»** — уточните текстовый результат («короче», «смелее», своими словами) без новой генерации с нуля;
- **«Персонажи»** — библиотека героев (фото + промпт внешности). Выберите персонажа в форме — он
  подставится в промпты, картинки и видео, и внешность не будет «плыть».
- Генерации идут в фоне: приложение можно закрыть, результат придёт в чат и сохранится в истории.

> 💰 Видео (Veo/Omni) и дубляж — самые дорогие операции: оплата за каждую секунду ролика. Текст и картинки — копейки.

---

## 1. Что понадобится

| Что | Где взять |
|---|---|
| Токен бота | [@BotFather](https://t.me/BotFather) → `/newbot` |
| Ваш Telegram ID | [@userinfobot](https://t.me/userinfobot) |
| Claude | https://console.anthropic.com/settings/keys |
| ChatGPT / GPT Image | https://platform.openai.com/api-keys |
| Gemini | https://aistudio.google.com/apikey |
| ElevenLabs | https://elevenlabs.io/app/settings/api-keys |

Не обязательно подключать всё сразу: раздел без ключа просто станет неактивным.
Но **Gemini** очень желателен — только он умеет смотреть видео.

> Никому не отправляйте ключи и не коммитьте файл `.env` в GitHub.

---

## 2. Деплой на Railway (рекомендуется, проще всего)

1. Зарегистрируйтесь на https://railway.com через GitHub.
2. **New Project → Deploy from GitHub repo →** выберите `myaihelper`.
3. Откройте сервис → вкладка **Variables** → добавьте переменные:
   ```
   BOT_TOKEN=...
   ALLOWED_USER_IDS=ваш_ID
   ANTHROPIC_API_KEY=...
   OPENAI_API_KEY=...
   GEMINI_API_KEY=...
   ELEVENLABS_API_KEY=...
   ```
4. Вкладка **Settings → Networking → Generate Domain**. Railway выдаст адрес вида
   `myaihelper-production.up.railway.app` — бот подхватит его сам (`WEBAPP_URL` указывать не нужно).
5. Дождитесь окончания деплоя (вкладка **Deployments**, статус *Active*).
6. Напишите боту `/start` → нажмите **🚀 Открыть**.

Обновление: любой `git push` в ветку, подключённую в Railway, пересобирает бота автоматически.

## 3. Деплой на Render

1. https://render.com → **New → Blueprint** → выберите репозиторий (используется `render.yaml`).
2. Заполните переменные (как в шаге 3 для Railway).
3. После деплоя напишите боту `/start`.

> Бесплатный тариф Render «засыпает» через 15 минут без запросов — вместе с ним засыпает и бот.
> Для постоянной работы нужен тариф Starter (указан в `render.yaml`).

## 4. Деплой на свой VPS (Docker + автоматический HTTPS)

Нужен VPS (Ubuntu 22.04+) и домен (или бесплатный поддомен, например на https://www.duckdns.org),
у которого A-запись указывает на IP сервера.

```bash
# 1. Установить Docker
curl -fsSL https://get.docker.com | sh

# 2. Скачать проект
git clone https://github.com/artstudiouzb-gif/myaihelper.git
cd myaihelper

# 3. Настроить
cp .env.example .env
nano .env        # заполнить ключи, DOMAIN=bot.example.com, WEBAPP_URL=https://bot.example.com

# 4. Запустить
docker compose up -d --build

# Логи / обновление
docker compose logs -f bot
git pull && docker compose up -d --build
```

Caddy сам получит HTTPS-сертификат для домена.

## 5. Локальная проверка интерфейса (без Telegram)

```bash
pip install -r requirements.txt
cp .env.example .env   # заполнить хотя бы BOT_TOKEN и ALLOWED_USER_IDS
DEV_SKIP_AUTH=1 python -m bot.main
# открыть http://localhost:8080
```

`DEV_SKIP_AUTH=1` отключает проверку Telegram — **никогда не включайте это на сервере**.
Чтобы открыть Mini App из Telegram с компьютера, нужен HTTPS-туннель, например
`cloudflared tunnel --url http://localhost:8080` (полученный адрес укажите в `WEBAPP_URL`).

---

## Безопасность

- Mini App проверяет цифровую подпись Telegram (`initData`) — подделать запрос с чужого устройства нельзя.
- Пользоваться ботом могут только ID из `ALLOWED_USER_IDS`. Остальным бот ответит, что он личный,
  и покажет их ID (удобно, чтобы узнать свой).
- Ключи хранятся только в переменных окружения сервера и никогда не попадают в браузер.

## Модели (актуальны на октябрь 2026)

| Задача | Модель по умолчанию | Переменная |
|---|---|---|
| Текст — Claude | `claude-opus-5-5` (effort `high`, автозамена при отказе) | `CLAUDE_MODEL`, `CLAUDE_EFFORT` |
| Текст — ChatGPT | `gpt-6.1-sol` (reasoning `medium`) | `OPENAI_MODEL`, `OPENAI_REASONING` |
| Текст и анализ видео — Gemini | `gemini-3.8-flash` | `GEMINI_MODEL` |
| Картинки — OpenAI | `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` | `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_MODEL_HQ` |
| Картинки — Google | `gemini-3.1-flash-image` (Nano Banana 2) / `gemini-3-pro-image` (Pro) | `GEMINI_IMAGE_MODEL`, `GEMINI_IMAGE_MODEL_PRO` |
| Видео | `veo-3.1-generate-001`, `veo-3.1-fast-generate-001`, `gemini-omni-1.1-flash` | `VEO_MODEL`, `VEO_FAST_MODEL`, `OMNI_MODEL` |
| Озвучка | `eleven_v4` / `eleven_v4_turbo` | `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_TTS_FAST_MODEL` |
| Дубляж / замена голоса / расшифровка | `dubbing_v2` / `eleven_multilingual_sts_v2` / `scribe_v2` | `ELEVENLABS_DUBBING_MODEL`, `ELEVENLABS_STS_MODEL`, `ELEVENLABS_STT_MODEL` |

Когда выйдут новые модели, достаточно поменять переменную — код трогать не нужно.

> Sora API OpenAI закрыл 24.09.2026, а Gemini 2.5 Google отключает 16.10.2026 — поэтому бот на них не опирается.

## Частые проблемы

| Проблема | Решение |
|---|---|
| Бот пишет «Это личный бот» | Добавьте свой ID в `ALLOWED_USER_IDS` и перезапустите |
| «Не задан WEBAPP_URL» | Railway: сгенерируйте домен (Settings → Networking). VPS: укажите `WEBAPP_URL=https://…` |
| «Откройте приложение через Telegram-бота» | Страница открыта в обычном браузере — откройте через кнопку в боте |
| Ошибка про баланс / `insufficient_quota` / 401 | Проверьте ключ и пополните баланс у провайдера |
| GPT Image: ошибка про verification | Подтвердите организацию: https://platform.openai.com/settings/organization/general |
| Клонирование голоса не работает | Нужен платный тариф ElevenLabs (Starter и выше) |
| Модель «не найдена» | Укажите актуальное имя модели в переменных `*_MODEL` |
| Veo: ошибка доступа | Генерация видео в Gemini API платная — подключите биллинг в Google AI Studio |
| Omni: ошибка доступа | Gemini Omni Flash — платная модель, нужен биллинг в Google AI Studio |
| Дубляж: язык не поддерживается | Dubbing v2 знает 90+ языков (узбекский тоже); если ошибка — попробуйте другой |
| Субтитры без кириллицы (локально) | Установите шрифты: `apt install fonts-montserrat fonts-noto-core` (в Docker уже есть) |
| Персонажи пропали | Библиотека хранится в браузере Telegram на устройстве; очистка кэша Telegram её удаляет |

## Структура

```
bot/
  main.py       — запуск бота (polling) и веб-сервера
  config.py     — настройки из переменных окружения
  auth.py       — проверка подписи Telegram и белого списка
  tools.py      — все 15 разделов: поля форм, промпты, логика
  web.py        — API для Mini App
  ai/llm.py     — Claude / ChatGPT / Gemini (текст, фото, видео)
  ai/images.py  — картинки: GPT Image 2.5, Nano Banana 2 / Pro
  ai/voice.py   — ElevenLabs: Eleven v4, клон, замена голоса, Dubbing v2, Scribe v2
  ai/video.py   — видео: Veo 3.1 и Gemini Omni Flash (генерация, редактирование, продление)
  ai/subtitles.py — анимированные субтитры (ASS) и SRT из пословной расшифровки
  ai/media.py   — ffmpeg: звук, кадры, склейка, вшивание субтитров
webapp/         — интерфейс Mini App (HTML/CSS/JS без сборки)
```

Новый раздел добавляется одной записью в `TOOLS` в `bot/tools.py` — интерфейс построится сам.
