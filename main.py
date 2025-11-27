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
        return JSONResponse({"error":"invalid_json"}, status_code=400)
    
    if not payload:
        log(f"❌ empty_payload")
        return JSONResponse({"error":"empty_payload"}, status_code=400)
    
    log(f"📥 webhook {payload}")
    
    # ---- Validate campaign ----
    cid = payload.get("campaign_id") or payload.get("campaign_uuid") or payload.get("campaign")
    if cid!=ALLOWED_CAMPAIGN_ID: 
        return {"ignored":"wrong_campaign"}
    
    uuid    = payload.get("email_id") or payload.get("email_uuid") or payload.get("id")
    link    = payload.get("link") or payload.get("url") or payload.get("clicked_url")
    subject = payload.get("subject") or payload.get("email_subject") or "Loan status"
    
    # Only process if we have a link (click events have links)
    if not uuid or not link:
        return {"ignored":"no_link"}
    
    # Extract ?c=option
    from urllib.parse import urlparse, parse_qs
    try:
        choice = parse_qs(urlparse(link).query).get("c",[None])[0]
    except Exception as e:
        log(f"❌ parse_error link={link} error={str(e)}")
        return {"error":"parse_error"}
    
    if not choice or choice not in ALL:
        return {"ignored":"invalid_choice"}
    
    remaining=[c for c in ALL if c!=choice]
    html=build_html(choice,remaining)
    
    # send thread-reply async (return 200 immediately)
    import asyncio; asyncio.create_task(reply(uuid,subject,html))
    
    return {"ok":True,"next":remaining}

# ========== NO-PAGE CLICK ENDPOINT ==========
@app.get("/qr")
def qr_click(): 
    return PlainTextResponse("",status_code=204)  # invisible

# ========== LOGS UI ==========
@app.get("/logs")
def logs(): return LOGS

