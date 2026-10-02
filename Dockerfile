FROM python:3.12-slim

# ffmpeg нужен, чтобы извлекать звук из видео и вставлять новый голос обратно
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY webapp ./webapp

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "bot.main"]
