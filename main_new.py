"""Main FastAPI application entry point"""
import asyncio
from fastapi import FastAPI

from config import *
from storage import get_queue
from logger import log
from middleware import log_requests
from routes import register_routes
from instantly_api import process_api_request_queue

# Create FastAPI app
app = FastAPI()

# Register middleware
@app.middleware("http")
async def middleware_wrapper(request, call_next):
    return await log_requests(request, call_next)

# Register all routes
register_routes(app)


@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup"""
    get_queue()
    asyncio.create_task(process_api_request_queue())
    log(f"🚀 APP_STARTUP: Queue processor started")

