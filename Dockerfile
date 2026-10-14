# Multi-stage production container for MusicMaid (Discord Music Bot) on Render
FROM python:3.11-slim

# Prevent Python buffering and interactive prompts
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies: FFmpeg, libopus, build tools, curl, git
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    nodejs \
    build-essential \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Verify system FFmpeg installation
RUN ffmpeg -version

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy bot application source code
COPY . .

# Expose HTTP port for Render health checks and Web Player ($PORT dynamically set by Render)
EXPOSE 10000

# Start command
CMD ["python", "main.py"]
