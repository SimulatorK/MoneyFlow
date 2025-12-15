#!/bin/bash
# =============================================================================
# MoneyFlow Application Runner
# =============================================================================
# This script manages both the FastAPI server and ngrok tunnel
# with optional periodic refresh to keep services running smoothly.
#
# Usage:
#   ./run.sh              # Start in development mode (default)
#   ./run.sh --prod       # Start in production mode (4 workers)
#   ./run.sh --ssl        # Start with SSL/HTTPS enabled
#   ./run.sh --refresh    # Enable periodic refresh (every 6 hours)
#   ./run.sh --prod --ssl # Production with SSL
#   ./run.sh --stop       # Stop all running services
#   ./run.sh --status     # Check status of services
#
# Environment variables:
#   SSL_KEYFILE   - Path to SSL private key (default: ./certs/privkey.pem)
#   SSL_CERTFILE  - Path to SSL certificate (default: ./certs/fullchain.pem)
#   SSL_PORT      - HTTPS port (default: 8443)
#
# =============================================================================

set -e

# Configuration
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$APP_DIR/.pids"
LOG_DIR="$APP_DIR/logs"
CERT_DIR="$APP_DIR/certs"
PORT="${PORT:-8000}"
SSL_PORT="${SSL_PORT:-8443}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-4}"
REFRESH_INTERVAL="${REFRESH_INTERVAL:-21600}"  # 6 hours in seconds
SSL_KEYFILE="${SSL_KEYFILE:-$CERT_DIR/privkey.pem}"
SSL_CERTFILE="${SSL_CERTFILE:-$CERT_DIR/fullchain.pem}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create directories
mkdir -p "$PID_DIR"
mkdir -p "$LOG_DIR"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if a process is running
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Get ngrok public URL
get_ngrok_url() {
    sleep 2  # Wait for ngrok to start
    local url=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"[^"]*"' | head -1 | cut -d'"' -f4)
    echo "$url"
}

# Start the uvicorn server
start_uvicorn() {
    local mode="$1"
    local use_ssl="$2"
    
    if is_running "$PID_DIR/uvicorn.pid"; then
        log_warn "Uvicorn is already running (PID: $(cat $PID_DIR/uvicorn.pid))"
        return 0
    fi
    
    cd "$APP_DIR"
    
    # Build base uvicorn command
    local UVICORN_CMD="poetry run uvicorn app.main:app --host $HOST"
    
    # Add SSL if enabled
    if [ "$use_ssl" = "ssl" ]; then
        if [ -f "$SSL_KEYFILE" ] && [ -f "$SSL_CERTFILE" ]; then
            log_info "SSL enabled - using HTTPS on port $SSL_PORT"
            UVICORN_CMD="$UVICORN_CMD --port $SSL_PORT --ssl-keyfile=$SSL_KEYFILE --ssl-certfile=$SSL_CERTFILE"
        else
            log_error "SSL certificates not found!"
            log_error "Expected: $SSL_KEYFILE and $SSL_CERTFILE"
            log_info "Generate self-signed certs with:"
            log_info "  mkdir -p certs && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\"
            log_info "    -keyout certs/privkey.pem -out certs/fullchain.pem -subj '/CN=localhost'"
            return 1
        fi
    else
        UVICORN_CMD="$UVICORN_CMD --port $PORT"
    fi
    
    # Add mode-specific options
    if [ "$mode" = "prod" ]; then
        log_info "Production mode: $WORKERS workers, no reload"
        UVICORN_CMD="$UVICORN_CMD --workers $WORKERS"
    else
        log_info "Development mode: auto-reload enabled"
        UVICORN_CMD="$UVICORN_CMD --reload"
    fi
    
    log_info "Starting: $UVICORN_CMD"
    
    # Run the command
    $UVICORN_CMD >> "$LOG_DIR/uvicorn.log" 2>&1 &
    
    local pid=$!
    echo $pid > "$PID_DIR/uvicorn.pid"
    
    # Wait a moment and check if it started
    sleep 2
    if is_running "$PID_DIR/uvicorn.pid"; then
        if [ "$use_ssl" = "ssl" ]; then
            log_success "Uvicorn started with HTTPS (PID: $pid)"
            log_success "Access at: https://localhost:$SSL_PORT"
        else
            log_success "Uvicorn started (PID: $pid)"
            log_success "Access at: http://localhost:$PORT"
        fi
        return 0
    else
        log_error "Failed to start uvicorn. Check $LOG_DIR/uvicorn.log"
        return 1
    fi
}

# Start ngrok tunnel
start_ngrok() {
    if is_running "$PID_DIR/ngrok.pid"; then
        log_warn "ngrok is already running (PID: $(cat $PID_DIR/ngrok.pid))"
        return 0
    fi
    
    # Check if ngrok is installed
    if ! command -v ngrok &> /dev/null; then
        log_error "ngrok is not installed. Install with: brew install ngrok"
        log_warn "Continuing without ngrok..."
        return 1
    fi
    
    log_info "Starting ngrok tunnel for port $PORT..."
    
    ngrok http "http://localhost:$PORT" \
        --log=stdout \
        >> "$LOG_DIR/ngrok.log" 2>&1 &
    
    local pid=$!
    echo $pid > "$PID_DIR/ngrok.pid"
    
    # Wait for ngrok to start and get URL
    sleep 3
    if is_running "$PID_DIR/ngrok.pid"; then
        local url=$(get_ngrok_url)
        log_success "ngrok started (PID: $pid)"
        if [ -n "$url" ]; then
            echo ""
            log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            log_success "🌐 Public URL: $url"
            log_success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            # Save URL to file for reference
            echo "$url" > "$APP_DIR/.ngrok_url"
        else
            log_warn "Could not retrieve ngrok URL. Check http://localhost:4040"
        fi
        return 0
    else
        log_error "Failed to start ngrok. Check $LOG_DIR/ngrok.log"
        return 1
    fi
}

# Stop a service
stop_service() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_info "Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 1
            # Force kill if still running
            if ps -p "$pid" > /dev/null 2>&1; then
                kill -9 "$pid" 2>/dev/null || true
            fi
            log_success "$name stopped"
        fi
        rm -f "$pid_file"
    else
        log_info "$name is not running"
    fi
}

# Stop all services
stop_all() {
    log_info "Stopping all services..."
    stop_service "ngrok"
    stop_service "uvicorn"
    # Also kill any orphaned processes
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "ngrok http" 2>/dev/null || true
    log_success "All services stopped"
}

# Restart all services
restart_all() {
    local mode="$1"
    log_info "Restarting services..."
    stop_all
    sleep 2
    start_uvicorn "$mode"
    start_ngrok
}

# Show status
show_status() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  MoneyFlow Service Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if is_running "$PID_DIR/uvicorn.pid"; then
        echo -e "  Uvicorn:  ${GREEN}● Running${NC} (PID: $(cat $PID_DIR/uvicorn.pid))"
        echo "            http://localhost:$PORT"
    else
        echo -e "  Uvicorn:  ${RED}○ Stopped${NC}"
    fi
    
    if is_running "$PID_DIR/ngrok.pid"; then
        echo -e "  ngrok:    ${GREEN}● Running${NC} (PID: $(cat $PID_DIR/ngrok.pid))"
        if [ -f "$APP_DIR/.ngrok_url" ]; then
            echo "            $(cat $APP_DIR/.ngrok_url)"
        fi
    else
        echo -e "  ngrok:    ${RED}○ Stopped${NC}"
    fi
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# Periodic refresh loop
refresh_loop() {
    local mode="$1"
    local interval="$2"
    
    log_info "Periodic refresh enabled (every $(($interval / 3600)) hours)"
    
    while true; do
        sleep "$interval"
        log_info "Performing scheduled refresh..."
        restart_all "$mode"
    done
}

# Main function
main() {
    local mode="dev"
    local use_ssl=""
    local enable_refresh=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --prod|--production)
                mode="prod"
                shift
                ;;
            --ssl|--https)
                use_ssl="ssl"
                shift
                ;;
            --refresh)
                enable_refresh=true
                shift
                ;;
            --stop)
                stop_all
                exit 0
                ;;
            --status)
                show_status
                exit 0
                ;;
            --restart)
                restart_all "$mode"
                exit 0
                ;;
            --help|-h)
                echo "MoneyFlow Application Runner v2.0.0"
                echo ""
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --prod, --production   Run in production mode (multiple workers)"
                echo "  --ssl, --https         Enable SSL/HTTPS"
                echo "  --refresh              Enable periodic refresh (every 6 hours)"
                echo "  --stop                 Stop all running services"
                echo "  --status               Show status of services"
                echo "  --restart              Restart all services"
                echo "  -h, --help             Show this help message"
                echo ""
                echo "Environment Variables:"
                echo "  PORT                   HTTP port (default: 8000)"
                echo "  SSL_PORT               HTTPS port (default: 8443)"
                echo "  HOST                   Server host (default: 0.0.0.0)"
                echo "  WORKERS                Number of workers in prod mode (default: 4)"
                echo "  REFRESH_INTERVAL       Refresh interval in seconds (default: 21600 = 6h)"
                echo "  SSL_KEYFILE            Path to SSL private key"
                echo "  SSL_CERTFILE           Path to SSL certificate"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Banner
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  💸 MoneyFlow Application Runner v2.0.0"
    echo "  Mode: $([ "$mode" = "prod" ] && echo "Production" || echo "Development")"
    echo "  SSL: $([ "$use_ssl" = "ssl" ] && echo "Enabled (HTTPS)" || echo "Disabled (HTTP)")"
    echo "  Refresh: $([ "$enable_refresh" = true ] && echo "Enabled (every 6h)" || echo "Disabled")"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Start services
    start_uvicorn "$mode" "$use_ssl"
    start_ngrok
    
    # Show status
    show_status
    
    log_info "Logs: $LOG_DIR/"
    log_info "Stop with: $0 --stop"
    
    # Start refresh loop if enabled
    if [ "$enable_refresh" = true ]; then
        log_info "Starting refresh loop in background..."
        refresh_loop "$mode" "$REFRESH_INTERVAL" &
        echo $! > "$PID_DIR/refresh.pid"
    fi
    
    # Keep script running to show logs
    if [ "$enable_refresh" = true ]; then
        log_info "Press Ctrl+C to stop all services"
        trap 'stop_all; exit 0' SIGINT SIGTERM
        
        # Tail the logs
        tail -f "$LOG_DIR/uvicorn.log" 2>/dev/null &
        wait
    fi
}

# Run main function
main "$@"

