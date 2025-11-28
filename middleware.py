"""FastAPI middleware for request logging"""
from fastapi import Request
from config import PATH_TO_CHOICE, NON_EMAIL_PATHS
from logger import log


def is_email_click_path(path: str) -> bool:
    """Check if path is an email click tracking path"""
    path_lower = path.lower().strip("/")
    if path in NON_EMAIL_PATHS or any(path.startswith(excluded) for excluded in NON_EMAIL_PATHS):
        return False
    return path_lower in PATH_TO_CHOICE or any(path.startswith(f"/{choice}") for choice in PATH_TO_CHOICE.keys())


async def log_requests(request: Request, call_next):
    """Middleware to log email click tracking GET requests and webhooks"""
    host = request.headers.get("host", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    
    if request.method == "GET" and is_email_click_path(request.url.path):
        query_params = dict(request.query_params)
        query_str = "?" + "&".join([f"{k}={v}" for k, v in query_params.items()]) if query_params else ""
        log(f"🌐 EMAIL_CLICK_REQUEST: GET {request.url.path}{query_str} | Host: {host} | Client: {client_ip}")
    
    if request.url.path == "/webhook/instantly":
        log(f"📋 WEBHOOK_RECEIVED: {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    if request.method == "GET" and is_email_click_path(request.url.path):
        log(f"📤 EMAIL_CLICK_RESPONSE: GET {request.url.path} -> {response.status_code}")
    elif request.url.path == "/webhook/instantly":
        log(f"⚡ WEBHOOK_RESPONSE: {response.status_code} (processed in background)")
    
    return response

