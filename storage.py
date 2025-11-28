"""Data storage - caches, queues, and state management"""
import asyncio
from typing import Dict, Any, Optional, List
from collections import deque

from config import MAX_QUEUE_SIZE

# ───────── LOG BUFFER ─────────
LOGS = deque(maxlen=800)

# ───────── EMAIL CLICK STORAGE ─────────
RECENT_EMAIL_CLICKS: Dict[str, Dict[str, Any]] = {}

# ───────── UUID CACHE ─────────
UUID_CACHE: Dict[str, Dict[str, Any]] = {}

# ───────── API REQUEST QUEUE ─────────
_api_request_queue: Optional[asyncio.Queue] = None
QUEUE_PROCESSOR_RUNNING = False
REQUEST_TIMESTAMPS: deque = deque(maxlen=18)

# ───────── PENDING WEBHOOKS ─────────
PENDING_WEBHOOKS: Dict[str, List[Dict[str, Any]]] = {}


def get_queue() -> asyncio.Queue:
    """Get or create the API request queue"""
    global _api_request_queue
    if _api_request_queue is None:
        _api_request_queue = asyncio.Queue()
    return _api_request_queue

