# Pin the Python base image directly. Home Assistant's default add-on base
# (ghcr.io/home-assistant/base) is Alpine without Python, so a BUILD_FROM-driven
# build fails with "pip: not found". BUILD_FROM is still declared so the
# Supervisor's build-arg is accepted, but the FROM below intentionally ignores it.
ARG BUILD_FROM=python:3.12-slim
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    REEL_TOGETHER_DB=/data/reel_together.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8099

# Home Assistant persists /data across restarts; the SQLite DB lives there.
CMD ["python", "-m", "app.server"]
