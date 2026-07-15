# ── Kuro Sōden (黒送伝) — Standalone Docker image ─────────────────────────
FROM python:3.12-slim

# System deps: ffmpeg (media), mkvtoolnix (mkv metadata), playwright (thumbnails)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mkvtoolnix \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Playwright (Chromium for thumbnail rendering)
RUN pip install playwright -q && playwright install --with-deps chromium

WORKDIR /app

# Layer 1: install wheel deps first (cached unless deps change)
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e .

# Layer 2: app code (fast to rebuild)
COPY . .

# Runtime paths
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

VOLUME ["/data/storage", "/data/sessions"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import asyncio; asyncio.get_event_loop()" || exit 1

CMD ["python", "main.py"]
