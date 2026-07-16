# Use Python 3.11 slim to minimise image size while keeping system libs available
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system-level build dependencies needed by:
#   - asyncpg  → libpq-dev
#   - pdfplumber/Pillow → gcc, libpoppler-cpp-dev (for pdfminer native ext)
#
# We install build tools, compile Python deps, then remove build tools in a
# single RUN layer to keep the final image lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
        libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Copy dependency manifest first so Docker cache is invalidated only when
# dependencies change — not on every source code change.
COPY pyproject.toml .

# Install runtime dependencies (no dev extras in the image)
RUN pip install --no-cache-dir -e "."

# Copy application source last (most frequently changing layer)
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini .

EXPOSE 8000

# Switch to non-root user
USER appuser

# Default command: production-ready (no --reload, multiple workers)
# Override in docker-compose.yml for development (--reload, 1 worker)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
