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

# Middleware to log ALL incoming requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    log(f"🌐 REQUEST: {request.method} {request.url.path} | Client: {request.client.host if request.client else 'unknown'}")
    
    # Log headers for webhook requests
    if request.url.path == "/webhook/instantly":
        headers_dict = dict(request.headers)
        log(f"📋 HEADERS: {json.dumps(headers_dict, indent=2)}")
    
    response = await call_next(request)
    log(f"📤 RESPONSE: {request.method} {request.url.path} -> {response.status_code}")
    return response

@app.post("/webhook/instantly")
async def instantly_webhook(req: Request):
    log(f"🔔 Webhook endpoint called at {datetime.now().isoformat()}")
    
    try:
        payload = await req.json()
    except Exception as e:
        body = await req.body()
        body_str = body.decode('utf-8', errors='ignore')[:200] if body else "(empty)"
        log(f"❌ invalid_json error={str(e)} body={body_str}")
        return {"ok":True}
    
    if not payload:
        log(f"⚠️ empty_payload_received")
        return {"ok":True}
    
    # Log detailed webhook information (handling Instantly.ai actual payload structure)
    event_type = payload.get("event_type") or payload.get("event") or payload.get("type") or "unknown"
    recipient = payload.get("lead_email") or payload.get("email") or payload.get("recipient") or "unknown"
    campaign_id = payload.get("campaign_id") or "unknown"
    campaign_name = payload.get("campaign_name") or "unknown"
    workspace = payload.get("workspace") or "unknown"
    step = payload.get("step") or "unknown"
    email_account = payload.get("email_account") or "unknown"
    
    # Note: Instantly.ai doesn't include the clicked URL in the webhook payload
    # The actual click goes to /qr endpoint which we log separately
    log(f"📥 WEBHOOK EVENT: {event_type}")
    log(f"   👤 Lead Email: {recipient}")
    log(f"   📧 Email Account: {email_account}")
    log(f"   📋 Campaign: {campaign_name} ({campaign_id})")
    log(f"   🔢 Step: {step} | Workspace: {workspace}")
    log(f"📦 FULL_PAYLOAD: {json.dumps(payload, indent=2)}")
    
    # Check if this is a click event
    if "click" in event_type.lower():
        log(f"✅ LINK_CLICK_WEBHOOK_RECEIVED from Instantly.ai")
        log(f"⚠️ NOTE: The clicked URL is not in webhook payload. Check /qr logs for which link was clicked.")
    
    # No actions taken - just log and return success
    return {"ok":True}

# ========== NO-PAGE CLICK ENDPOINT ==========
@app.get("/qr")
def qr_click(request: Request): 
    # Log when someone clicks a link
    query_params = dict(request.query_params)
    choice = query_params.get("c") or query_params.get("choice") or "unknown"
    log(f"🔗 LINK_CLICKED: /qr?c={choice} | Params: {query_params} | IP: {request.client.host if request.client else 'unknown'}")
    log(f"⚠️ NOTE: This is a direct link click. Instantly.ai should send a webhook to /webhook/instantly for tracking.")
    return PlainTextResponse("",status_code=204)  # invisible

# ========== LOGS UI ==========
@app.get("/logs")
def logs(): 
    return list(LOGS)

@app.post("/logs/clear")
def clear_logs():
    LOGS.clear()
    return {"ok": True, "message": "Logs cleared"}

@app.get("/status")
def status():
    """Check webhook configuration status"""
    return {
        "webhook_url": f"https://emailquickreplies.onrender.com/webhook/instantly",
        "campaign_id": ALLOWED_CAMPAIGN_ID,
        "frontend_action_base": FRONTEND_ACTION_BASE,
        "logs_count": len(LOGS),
        "recent_events": list(LOGS)[-10:] if LOGS else []
    }

@app.get("/test")
def test_page():
    """Test page with clickable links to test tracking"""
    html = f"""
    <html>
    <head><title>Link Tracking Test</title></head>
    <body>
        <h1>Link Tracking Test Page</h1>
        <p>Click any link below. If Instantly.ai tracking works, you should see a webhook in /logs</p>
        <hr>
        <h2>Test Links:</h2>
        <a href="{FRONTEND_ACTION_BASE}?c=close_loan" target="_blank">🔵 Close my loan</a><br><br>
        <a href="{FRONTEND_ACTION_BASE}?c=settle_loan" target="_blank">💠 Settle my loan</a><br><br>
        <a href="{FRONTEND_ACTION_BASE}?c=never_pay" target="_blank">⚠️ I will never pay</a><br><br>
        <a href="{FRONTEND_ACTION_BASE}?c=need_more_time" target="_blank">⏳ Need more time</a><br><br>
        <hr>
        <h2>Check Results:</h2>
        <a href="/logs" target="_blank">View Logs</a> | 
        <a href="/status" target="_blank">View Status</a> | 
        <a href="/test/webhook" target="_blank">Simulate Webhook</a>
    </body>
    </html>
    """
    return HTMLResponse(html)

@app.post("/test/webhook")
def test_webhook():
    """Simulate an Instantly.ai webhook for testing (using actual payload structure)"""
    test_payload = {
        "step": 1,
        "email": "test@example.com",
        "variant": 1,
        "timestamp": datetime.now().isoformat(),
        "workspace": "test-workspace-12345",
        "event_type": "link_clicked",
        "lead_email": "test@example.com",
        "unibox_url": None,
        "campaign_id": ALLOWED_CAMPAIGN_ID,
        "campaign_name": "Test Campaign",
        "email_account": INSTANTLY_EACCOUNT or "test@example.com"
    }
    
    # Manually trigger the webhook handler logic
    log(f"🧪 TEST_WEBHOOK_SIMULATED")
    event_type = test_payload.get("event_type") or "test"
    recipient = test_payload.get("lead_email") or "test@example.com"
    campaign_id = test_payload.get("campaign_id") or "test"
    campaign_name = test_payload.get("campaign_name") or "test"
    
    log(f"📥 WEBHOOK EVENT: {event_type}")
    log(f"   👤 Lead Email: {recipient}")
    log(f"   📧 Email Account: {test_payload.get('email_account')}")
    log(f"   📋 Campaign: {campaign_name} ({campaign_id})")
    log(f"📦 FULL_PAYLOAD: {json.dumps(test_payload, indent=2)}")
    
    if "click" in event_type.lower():
        log(f"✅ LINK_CLICK_WEBHOOK_RECEIVED from Instantly.ai (TEST)")
    
    return {
        "ok": True,
        "message": "Test webhook simulated",
        "payload": test_payload,
        "logs_url": "/logs"
    }

