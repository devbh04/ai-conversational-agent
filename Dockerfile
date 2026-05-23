# ══════════════════════════════════════════════════════════════════════════════
# Multi-stage Dockerfile — uses uv for fast, reproducible installs
# Stage 1: Build dependencies with uv
# Stage 2: Lean runtime image
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System deps for building native packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files and install deps with uv
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Only the runtime system deps needed (supervisor + CA certs)
RUN apt-get update && apt-get install -y \
    supervisor \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv in runtime too
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy project files
COPY pyproject.toml .
COPY . .

# Copy supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VIRTUAL_ENV=/app/.venv

# Expose UI port, backend port, and LiveKit agent port
EXPOSE 8000 8001 8081

# Start all services via supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
