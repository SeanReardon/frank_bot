# Use Python 3.11 slim image
FROM python:3.11-slim AS builder

# Install Poetry
ENV POETRY_VERSION=1.7.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir poetry==$POETRY_VERSION

WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev dependencies in production)
RUN poetry install --only=main --no-root

# Production image
FROM python:3.11-slim

WORKDIR /app

# Git commit hash baked in at build time
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

# Install Android Debug Bridge (adb) and curl for downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install gnirehtet for USB reverse tethering (phone internet via USB)
RUN curl -sL -o /tmp/gnirehtet.zip \
    "https://github.com/Genymobile/gnirehtet/releases/download/v2.5.1/gnirehtet-rust-linux64-v2.5.1.zip" \
    && unzip -o /tmp/gnirehtet.zip -d /tmp \
    && cp /tmp/gnirehtet-rust-linux64/gnirehtet /usr/local/bin/gnirehtet \
    && cp /tmp/gnirehtet-rust-linux64/gnirehtet.apk /app/gnirehtet.apk \
    && chmod +x /usr/local/bin/gnirehtet \
    && rm -rf /tmp/gnirehtet*

# Configure environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_FILE=~/logs/frank_bot-api.log \
    PORT=8000 \
    HOST=0.0.0.0 \
    PATH="/app/.venv/bin:$PATH"

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Make entrypoint executable
RUN chmod +x /app/scripts/entrypoint.sh

# Expose port for HTTP transport
EXPOSE 8000

# Entrypoint starts gnirehtet relay then launches the app
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
