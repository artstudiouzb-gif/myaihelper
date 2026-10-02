FROM python:3.12-slim

# ffmpeg — звук, кадры, дубляж и вшивание субтитров; шрифты с кириллицей — для анимированных субтитров
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-montserrat fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY webapp ./webapp

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "bot.main"]
