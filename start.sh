#!/bin/bash
# Production startup script

# Set default values
PORT=${PORT:-8000}
WORKERS=${WORKERS:-2}

# Start the server
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port $PORT \
    --workers $WORKERS \
    --log-level ${LOG_LEVEL:-info}

