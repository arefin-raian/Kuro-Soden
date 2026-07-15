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

# Layer 2: app code
COPY . .

# Editable install AFTER source is present so setuptools finds the package
RUN pip install --no-cache-dir -e .

# Runtime paths
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Persistent /data/storage + /data/sessions is wired through the host
# platform's volume mechanism (Render disk mount, Railway Volume, K8s PVC,
# or a mounted VM disk) — NOT declared as a Docker VOLUME so the image stays
# portable across Render / Railway / Docker-Compose / bare-metal.

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import asyncio; asyncio.get_event_loop()" || exit 1

CMD ["python", "main.py"]
