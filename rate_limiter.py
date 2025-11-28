"""Rate limiting utilities"""
import asyncio
from datetime import datetime
from storage import REQUEST_TIMESTAMPS
from config import RATE_LIMIT_REQUESTS_PER_MINUTE, RATE_LIMIT_WINDOW_SECONDS
from logger import log


async def wait_for_rate_limit():
    """Wait if we've hit the rate limit, clearing old timestamps"""
    now = datetime.now()
    # Remove timestamps older than the rate limit window
    while REQUEST_TIMESTAMPS and (now - REQUEST_TIMESTAMPS[0]).total_seconds() >= RATE_LIMIT_WINDOW_SECONDS:
        REQUEST_TIMESTAMPS.popleft()
    
    # If we're at the limit, wait until we can make another request
    if len(REQUEST_TIMESTAMPS) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
        oldest_ts = REQUEST_TIMESTAMPS[0]
        wait_seconds = RATE_LIMIT_WINDOW_SECONDS - (now - oldest_ts).total_seconds() + 1
        if wait_seconds > 0:
            log(f"⏳ RATE_LIMIT_WAIT: Waiting {wait_seconds:.1f}s before next API request (at limit)")
            await asyncio.sleep(wait_seconds)
            # Re-check and remove expired timestamps after waiting
            now = datetime.now()
            while REQUEST_TIMESTAMPS and (now - REQUEST_TIMESTAMPS[0]).total_seconds() >= RATE_LIMIT_WINDOW_SECONDS:
                REQUEST_TIMESTAMPS.popleft()
    
    # Record this request timestamp
    REQUEST_TIMESTAMPS.append(datetime.now())

