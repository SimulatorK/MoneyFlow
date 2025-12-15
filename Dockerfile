# =============================================================================
# MoneyFlow Dockerfile
# =============================================================================
# Multi-stage build for a lean, production-ready container
#
# Build: docker build -t moneyflow:2.0.0 .
# Run:   docker run -p 8000:8000 -v ./data:/app/data moneyflow:2.0.0
#
# =============================================================================

# Stage 1: Build stage with Poetry
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# Install Poetry
RUN pip install "poetry==$POETRY_VERSION"

# Set working directory
WORKDIR /app

# Copy dependency files first (for better caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (without dev dependencies)
RUN poetry install --only main --no-root

# Stage 2: Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    # Application settings
    PORT=8000 \
    HOST=0.0.0.0 \
    WORKERS=4 \
    # Security
    SSL_ENABLED=false \
    SSL_KEYFILE="" \
    SSL_CERTFILE=""

# Create non-root user for security
RUN groupadd -r moneyflow && useradd -r -g moneyflow moneyflow

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/certs && \
    chown -R moneyflow:moneyflow /app

# Copy and set permissions for entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER moneyflow

# Expose ports
EXPOSE 8000
EXPOSE 8443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/docs')" || exit 1

# Set entrypoint and default command
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

