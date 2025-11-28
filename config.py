"""Configuration and constants"""
import os
from dotenv import load_dotenv

load_dotenv()

# ───────── API CONFIG ─────────
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
INSTANTLY_EACCOUNT = os.getenv("INSTANTLY_EACCOUNT")
FRONTEND_ACTION_BASE = os.getenv("FRONTEND_ACTION_BASE", "https://l.riverlinedebtsupport.in")
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "https://riverline.credit")
INSTANTLY_URL = "https://api.instantly.ai/api/v2/emails/reply"

if not INSTANTLY_API_KEY or not INSTANTLY_EACCOUNT:
    raise RuntimeError("Missing INSTANTLY_API_KEY / INSTANTLY_EACCOUNT")

# ───────── STATELESS OPTIONS ─────────
CHOICE_LABELS = {
    "close_loan": "🔵 Close my loan",
    "settle_loan": "💠 Settle my loan",
    "never_pay": "⚠️ I will never pay",
    "need_more_time": "⏳ Need more time",
}

# Map URL paths to choice values
PATH_TO_CHOICE = {
    "settle": "settle_loan",
    "close": "close_loan",
    "never": "never_pay",
    "time": "need_more_time",
    "human": "need_more_time",
}

ALL = list(CHOICE_LABELS.keys())

CHOICE_COPY = {
    "close_loan": {"title": "You want to close your loan", "body": "We'll share closure steps shortly."},
    "settle_loan": {"title": "You want settlement", "body": "We'll evaluate and send a proposal."},
    "never_pay": {"title": "You cannot / won't pay", "body": "We understand — we'll review your case."},
    "need_more_time": {"title": "You need time", "body": "Noted. We'll share extension options."},
}

# ───────── PATHS ─────────
NON_EMAIL_PATHS = {"/logs", "/status", "/test", "/qr", "/favicon.ico", "/lt", "/webhook", "/robots.txt", "/.well-known"}

# ───────── RATE LIMITING ─────────
RATE_LIMIT_REQUESTS_PER_MINUTE = 18
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_QUEUE_SIZE = 1000

# ───────── CACHE TTLs ─────────
EMAIL_CLICK_TTL_SECONDS = 3600  # one hour safety window
UUID_CACHE_TTL_SECONDS = 3600  # Cache UUIDs for 1 hour
PENDING_WEBHOOK_TTL_SECONDS = 120  # Wait up to 2 minutes for click to arrive

