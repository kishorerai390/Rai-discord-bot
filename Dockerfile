# Production container for Rem (Discord Anime Music Companion) on Render
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    DENO_INSTALL=/usr/local/deno \
    PATH="/usr/local/deno/bin:${PATH}"

# FFmpeg/libopus for voice, Node + Deno for yt-dlp EJS challenge solving.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libopus0 libopus-dev nodejs build-essential curl git ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deno.land/install.sh | sh -s v2.1.4 \
    && deno --version && node --version && ffmpeg -version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 10000
CMD ["python", "main.py"]
