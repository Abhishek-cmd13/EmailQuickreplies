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
FRONTEND_ACTION_BASE  = os.getenv("FRONTEND_ACTION_BASE", "https://l.riverlinedebtsupport.in")
BACKEND_BASE_URL      = os.getenv("BACKEND_BASE_URL", "https://riverline.credit")
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

# Map URL paths to choice values
PATH_TO_CHOICE = {
    "settle": "settle_loan",
    "close": "close_loan",
    "never": "never_pay",
    "time": "need_more_time",
    "human": "need_more_time",  # If "human" is also an option
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

# ───────── TEMP STORAGE FOR CLICKS (to match with webhooks) ─────────
# Stores recent clicks: [(timestamp, choice, ip), ...]
RECENT_CLICKS = deque(maxlen=100)

async def find_email_id_for_lead(lead_email: str, campaign_id: str = None):
    """Try to find email_id for a lead using Instantly.ai API"""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            # Try to get campaign emails
            url = "https://api.instantly.ai/api/v2/emails/list"
            params = {"eaccount": INSTANTLY_EACCOUNT, "email": lead_email}
            if campaign_id:
                params["campaign_id"] = campaign_id
            
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            if r.status_code == 200:
                data = r.json()
                emails = data.get("emails", [])
                if emails:
                    # Get most recent email
                    latest = sorted(emails, key=lambda x: x.get("sent_at", ""), reverse=True)[0]
                    return latest.get("id") or latest.get("email_id")
    except Exception as e:
        log(f"⚠️ Could not fetch email_id: {str(e)}")
    return None

# ───────── BUILD EMAIL HTML ─────────
def build_html(choice, remaining):
    msg = CHOICE_COPY.get(choice,{"title":"Noted","body":"Response received"})
    
    # Map choice to URL path
    def choice_to_path(c):
        mapping = {
            "settle_loan": "settle",
            "close_loan": "close",
            "never_pay": "never",
            "need_more_time": "time"
        }
        return mapping.get(c, "unknown")
    
    next_btn = "".join(
        f'<a href="{FRONTEND_ACTION_BASE}/{choice_to_path(r)}">{CHOICE_LABELS[r]}</a><br>'
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
    host = request.headers.get("host", "unknown")
    log(f"🌐 REQUEST: {request.method} {request.url.path} | Host: {host} | Client: {request.client.host if request.client else 'unknown'}")
    
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
    
    log(f"📥 WEBHOOK EVENT: {event_type}")
    log(f"   👤 Lead Email: {recipient}")
    log(f"   📧 Email Account: {email_account}")
    log(f"   📋 Campaign: {campaign_name} ({campaign_id})")
    log(f"   🔢 Step: {step} | Workspace: {workspace}")
    log(f"📦 FULL_PAYLOAD: {json.dumps(payload, indent=2)}")
    
    # Check if this is a click event - send automatic reply
    if "click" in event_type.lower():
        log(f"✅ LINK_CLICK_WEBHOOK_RECEIVED from Instantly.ai")
        
        # Find most recent click within last 60 seconds
        now = datetime.now()
        matching_click = None
        for click_time, choice, ip in reversed(list(RECENT_CLICKS)):
            time_diff = (now - click_time).total_seconds()
            if time_diff < 60:  # Within last 60 seconds
                matching_click = choice
                log(f"📌 Matched with recent click: {choice} (from {time_diff:.1f}s ago)")
                break
        
        if matching_click:
            choice = matching_click
            
            # Try to get email_id from Instantly.ai API
            email_id = await find_email_id_for_lead(recipient, campaign_id)
            
            if email_id:
                # Get remaining choices
                remaining = [c for c in ALL if c != choice]
                html = build_html(choice, remaining)
                await reply(email_id, "Loan Update", html)
                log(f"✅ Reply sent for choice: {choice} to {recipient}")
            else:
                log(f"⚠️ Could not find email_id for {recipient}. Reply not sent.")
        else:
            log(f"⚠️ No recent click found (within 60s). Reply not sent.")
    
    return {"ok":True}


# ========== HANDLE INSTANTLY.AI TRACKING (if inst.riverline.credit points to us) ==========
@app.get("/lt/{tracking_path:path}")
async def handle_instantly_tracking(tracking_path: str, request: Request):
    """Handle Instantly.ai tracking redirects - redirect to original destination"""
    from urllib.parse import parse_qs, urlparse
    
    log(f"🔀 Instantly.ai tracking: /lt/{tracking_path}")
    log(f"   Query params: {dict(request.query_params)}")
    log(f"   Full URL: {request.url}")
    
    # Try to extract destination from query params (Instantly.ai might pass it)
    query_params = dict(request.query_params)
    destination = query_params.get("url") or query_params.get("destination") or query_params.get("redirect")
    
    if destination:
        log(f"📍 Found destination in params: {destination}")
        # Extract choice from destination URL
        parsed = urlparse(destination)
        choice_params = parse_qs(parsed.query)
        choice = choice_params.get("c", choice_params.get("choice", [None]))[0] or "unknown"
        
        if choice != "unknown":
            RECENT_CLICKS.append((datetime.now(), choice, request.client.host if request.client else "unknown"))
            log(f"💾 Stored choice {choice} from tracking redirect")
        
        # Redirect to the original destination
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=destination, status_code=302)
    
    # If no destination, try to parse from tracking path or referrer
    # This is a fallback - Instantly.ai should provide the destination
    log(f"⚠️ No destination found in tracking URL - Instantly.ai should redirect automatically")
    log(f"   If this persists, check Instantly.ai link tracking configuration")
    
    # Return 204 - let Instantly.ai handle the redirect if possible
    return PlainTextResponse("", status_code=204)

# ========== LEGACY QUERY PARAM ENDPOINT (for backwards compatibility) ==========
@app.get("/qr")
async def qr_click(request: Request): 
    # Log when someone clicks a link (legacy format)
    query_params = dict(request.query_params)
    choice = query_params.get("c") or query_params.get("choice") or "unknown"
    client_ip = request.client.host if request.client else "unknown"
    
    log(f"🔗 LINK_CLICKED (legacy): /qr?c={choice} | Params: {query_params} | IP: {client_ip}")
    
    # Store the click with timestamp - webhook will match within 60 seconds
    if choice != "unknown":
        RECENT_CLICKS.append((datetime.now(), choice, client_ip))
        log(f"💾 Stored choice {choice} - waiting for webhook (will match within 60s)")
    
    log(f"ℹ️ Instantly.ai will send webhook → automatic reply will be sent")
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
        "backend_base_url": BACKEND_BASE_URL,
        "click_endpoints": {
            "settle": f"{BACKEND_BASE_URL}/settle",
            "close": f"{BACKEND_BASE_URL}/close",
            "never": f"{BACKEND_BASE_URL}/never",
            "human": f"{BACKEND_BASE_URL}/human"
        },
        "email_links": {
            "settle": f"{FRONTEND_ACTION_BASE}/settle",
            "close": f"{FRONTEND_ACTION_BASE}/close",
            "never": f"{FRONTEND_ACTION_BASE}/never",
            "human": f"{FRONTEND_ACTION_BASE}/human"
        },
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

# ========== PATH-BASED CLICK ENDPOINT (must be last - catch-all route) ==========
@app.get("/{path_choice}")
async def link_click(path_choice: str, request: Request):
    """Handle path-based links like /settle, /close, /human - catch-all route at end"""
    client_ip = request.client.host if request.client else "unknown"
    
    # Map path to choice
    choice = PATH_TO_CHOICE.get(path_choice.lower(), "unknown")
    
    log(f"🔗 LINK_CLICKED: /{path_choice} → choice: {choice} | IP: {client_ip}")
    
    # Store the click with timestamp - webhook will match within 60 seconds
    if choice != "unknown":
        RECENT_CLICKS.append((datetime.now(), choice, client_ip))
        log(f"💾 Stored choice {choice} - waiting for webhook (will match within 60s)")
    else:
        log(f"⚠️ Unknown path choice: {path_choice}")
    
    log(f"ℹ️ Instantly.ai will send webhook → automatic reply will be sent")
    return PlainTextResponse("",status_code=204)  # invisible

