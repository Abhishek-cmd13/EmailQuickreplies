import os, logging, json
from datetime import datetime
from typing import Dict, Any, Optional, List
from collections import deque

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

# ───────── CONFIG ─────────
INSTANTLY_API_KEY     = os.getenv("INSTANTLY_API_KEY")
INSTANTLY_EACCOUNT    = os.getenv("INSTANTLY_EACCOUNT")
FRONTEND_ACTION_BASE  = os.getenv("FRONTEND_ACTION_BASE", "https://riverline.ai/qr")
ALLOWED_CAMPAIGN_ID   = "e205ce46-f772-42fd-a81c-40eaa996f54e"
INSTANTLY_URL         = "https://api.instantly.ai/api/v2/emails/reply"

if not INSTANTLY_API_KEY or not INSTANTLY_EACCOUNT:
    raise RuntimeError("Missing INSTANTLY_API_KEY / INSTANTLY_EACCOUNT")

# ───────── STATELESS OPTIONS ─────────
CHOICE_LABELS = {
    "close_loan": "🔵 Close my loan",
    "settle_loan": "💠 Settle my loan",
    "never_pay": "⚠️ I will never pay",
    "need_more_time": "⏳ Need more time",
}

ALL = list(CHOICE_LABELS.keys())

CHOICE_COPY = {
    "close_loan": {"title":"You want to close your loan","body":"We'll share closure steps shortly."},
    "settle_loan":{"title":"You want settlement","body":"We'll evaluate and send a proposal."},
    "never_pay":{"title":"You cannot / won't pay","body":"We understand — we'll review your case."},
    "need_more_time":{"title":"You need time","body":"Noted. We'll share extension options."},
}

# ───────── LOG BUFFER (UI readable) ─────────
LOGS = deque(maxlen=800)

def log(x): LOGS.append({"t":datetime.now().isoformat(),"m":x}); print(x)

# ───────── BUILD EMAIL HTML ─────────
def build_html(choice, remaining):
    msg = CHOICE_COPY.get(choice,{"title":"Noted","body":"Response received"})
    next_btn = "".join(
        f'<a href="{FRONTEND_ACTION_BASE}?c={r}">{CHOICE_LABELS[r]}</a><br>'
        for r in remaining
    ) if remaining else "<p>We'll follow up soon.</p>"
    return f"""
    <b>{msg['title']}</b><br>{msg['body']}<br><br>
    { f"Choose next: <br>{next_btn}" if remaining else "" }
    """

# ───────── SEND REPLY IN SAME THREAD ─────────
async def reply(uuid, subject, html):
    subject = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(INSTANTLY_URL, json={
            "reply_to_uuid":uuid,
            "eaccount":INSTANTLY_EACCOUNT,
            "subject":subject,
            "body":{"html":html}
        }, headers={"Authorization":f"Bearer {INSTANTLY_API_KEY}"})
        if r.status_code > 299: log(f"❌ reply_failed {r.text}")

# ========== WEBHOOK ==========
app = FastAPI()

@app.post("/webhook/instantly")
async def instantly_webhook(req: Request):
    try:
        payload = await req.json()
    except Exception as e:
        body = await req.body()
        body_str = body.decode('utf-8', errors='ignore')[:200] if body else "(empty)"
        log(f"❌ invalid_json error={str(e)} body={body_str}")
        return {"ok":True}
    
    log(f"📥 webhook {payload}")
    
    # No actions taken - just log and return success
    return {"ok":True}

# ========== NO-PAGE CLICK ENDPOINT ==========
@app.get("/qr")
def qr_click(): 
    return PlainTextResponse("",status_code=204)  # invisible

# ========== LOGS UI ==========
@app.get("/logs")
def logs(): 
    return list(LOGS)

@app.post("/logs/clear")
def clear_logs():
    LOGS.clear()
    return {"ok": True, "message": "Logs cleared"}

