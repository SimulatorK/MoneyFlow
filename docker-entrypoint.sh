#!/bin/bash
# =============================================================================
# MoneyFlow Docker Entrypoint
# =============================================================================
# Handles database migrations and starts the application
# =============================================================================

set -e

echo "=============================================="
echo "  MoneyFlow v2.0.0"
echo "=============================================="

# Run database migrations
echo "[*] Running database migrations..."
python -m alembic upgrade head 2>/dev/null || echo "[!] Migrations skipped (may already be applied)"

# Initialize database if needed
echo "[*] Initializing database..."
python -c "from app.db import init_db; init_db()" 2>/dev/null || echo "[!] Database initialization skipped"

# Build uvicorn command
UVICORN_CMD="uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"

# Add workers for production
if [ "${WORKERS:-1}" -gt 1 ]; then
    UVICORN_CMD="$UVICORN_CMD --workers ${WORKERS}"
fi

# Add SSL if enabled
if [ "${SSL_ENABLED}" = "true" ]; then
    if [ -n "${SSL_KEYFILE}" ] && [ -n "${SSL_CERTFILE}" ]; then
        echo "[*] SSL enabled with provided certificates"
        UVICORN_CMD="$UVICORN_CMD --ssl-keyfile=${SSL_KEYFILE} --ssl-certfile=${SSL_CERTFILE}"
        
        # Also set HTTPS port if different
        if [ -n "${SSL_PORT}" ]; then
            UVICORN_CMD="$UVICORN_CMD --port ${SSL_PORT}"
        fi
    else
        echo "[!] SSL_ENABLED=true but SSL_KEYFILE or SSL_CERTFILE not provided"
        echo "[!] Falling back to HTTP"
    fi
fi

# Add reload for development
if [ "${DEV_MODE}" = "true" ]; then
    UVICORN_CMD="$UVICORN_CMD --reload"
    echo "[*] Development mode enabled (auto-reload)"
fi

echo "[*] Starting MoneyFlow..."
echo "[*] Command: $UVICORN_CMD"
echo "=============================================="

# Execute the command (replace this process)
exec $UVICORN_CMD

