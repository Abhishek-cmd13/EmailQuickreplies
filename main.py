import os, logging, json
from datetime import datetime
from typing import Dict, Any, Optional, List
from collections import deque
from urllib.parse import quote_plus

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

# Store recent clicks keyed by email so we can match instantly via webhook
RECENT_EMAIL_CLICKS: Dict[str, Dict[str, Any]] = {}
# Fallback click history (time-based) to support old links without email param
RECENT_CLICKS = deque(maxlen=100)
EMAIL_CLICK_TTL_SECONDS = 3600  # one hour safety window

# Paths to exclude from email click tracking logs
NON_EMAIL_PATHS = {"/logs", "/status", "/test", "/qr", "/favicon.ico", "/lt", "/webhook", "/robots.txt", "/.well-known"}

def is_email_click_path(path: str) -> bool:
    """Check if path is an email click tracking path"""
    path_lower = path.lower().strip("/")
    if path in NON_EMAIL_PATHS or any(path.startswith(excluded) for excluded in NON_EMAIL_PATHS):
        return False
    # Check if it's one of our choice paths
    return path_lower in PATH_TO_CHOICE or any(path.startswith(f"/{choice}") for choice in PATH_TO_CHOICE.keys())

def log(x): LOGS.append({"t":datetime.now().isoformat(),"m":x}); print(x)

def store_email_click(email: str, choice: str, client_ip: str) -> None:
    """Store email→choice mapping for fast webhook matching."""
    if not email or not choice or choice == "unknown":
        return
    normalized = email.strip().lower()
    if not normalized:
        return
    now = datetime.now()
    RECENT_EMAIL_CLICKS[normalized] = {"choice": choice, "timestamp": now, "ip": client_ip}
    log(f"📧 EMAIL_STORED: Email '{normalized}' → Choice '{choice}' stored (IP: {client_ip})")
    # Prune stale entries
    cutoff_delta = EMAIL_CLICK_TTL_SECONDS
    pruned_count = 0
    for key, data in list(RECENT_EMAIL_CLICKS.items()):
        ts = data.get("timestamp")
        if ts and (now - ts).total_seconds() > cutoff_delta:
            del RECENT_EMAIL_CLICKS[key]
            pruned_count += 1
    if pruned_count > 0:
        log(f"🧹 EMAIL_STORAGE_CLEANUP: Pruned {pruned_count} stale email entries")

async def find_email_uuid_for_lead(eaccount: str, lead_email: str, campaign_id: str = None):
    """Try to find email uuid and subject for a lead using Instantly.ai API"""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            # Correct endpoint: /api/v2/emails (not /list)
            url = "https://api.instantly.ai/api/v2/emails"
            params = {
                "eaccount": eaccount,
                "lead": lead_email  # Use "lead" parameter, not "email"
            }
            if campaign_id:
                params["campaign_id"] = campaign_id
            
            log(f"🔍 API_CALL_START: GET {url}")
            log(f"📋 API_PARAMS: {params}")
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            
            log(f"📡 API_RESPONSE: Status {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                # API returns items array in response
                emails = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                log(f"📧 API_RESULT: Found {len(emails)} email(s) for {lead_email}")
                
                if emails:
                    # Sort by timestamp_created (most recent first)
                    emails.sort(key=lambda x: x.get("timestamp_created", x.get("timestamp_email", "")), reverse=True)
                    latest = emails[0]
                    # API returns "id" field as the uuid
                    uuid = latest.get("id")
                    # Try multiple possible subject fields from Instantly.ai API
                    subject = (latest.get("subject") or 
                              latest.get("email_subject") or 
                              latest.get("subject_line") or
                              latest.get("title") or
                              "")
                    
                    # Log all available fields for debugging
                    log(f"💡 DEBUG: Latest email keys: {list(latest.keys())}")
                    log(f"💡 DEBUG: Subject fields - subject='{latest.get('subject')}', email_subject='{latest.get('email_subject')}', subject_line='{latest.get('subject_line')}', title='{latest.get('title')}'")
                    
                    if not subject or not subject.strip():
                        log(f"⚠️ WARNING: Subject is empty in API response - this will cause threading issues")
                        log(f"💡 DEBUG: Full email object (first 500 chars): {json.dumps(latest, indent=2)[:500]}")
                        subject = "Loan Update"  # Fallback - but this is not ideal
                    else:
                        log(f"✅ UUID_FOUND: uuid={uuid}, subject={subject}")
                    
                    return uuid, subject
                else:
                    log(f"⚠️ UUID_NOT_FOUND: No emails found for {lead_email}")
                    log(f"💡 DEBUG: API returned data type: {type(data)}")
                    log(f"💡 DEBUG: Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                    log(f"💡 DEBUG: Response data: {json.dumps(data, indent=2)[:500]}")
            elif r.status_code == 429:
                error_text = r.text[:500] if r.text else "No error message"
                log(f"⚠️ API_RATE_LIMITED: Status 429 - Too Many Requests. Error: {error_text}")
                log(f"💡 RATE_LIMIT_INFO: Instantly.ai allows max 20 requests per minute. Waiting and retrying...")
                # Wait 3 seconds and retry once
                import asyncio
                await asyncio.sleep(3)
                log(f"🔄 API_RETRY: Retrying API call after rate limit delay...")
                r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
                log(f"📡 API_RESPONSE (retry): Status {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    emails = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    log(f"📧 API_RESULT (retry): Found {len(emails)} email(s) for {lead_email}")
                    if emails:
                        emails.sort(key=lambda x: x.get("timestamp_created", x.get("timestamp_email", "")), reverse=True)
                        latest = emails[0]
                        uuid = latest.get("id")
                        subject = latest.get("subject", "Loan Update")
                        log(f"✅ UUID_FOUND (retry): uuid={uuid}, subject={subject}")
                        return uuid, subject
                else:
                    error_text = r.text[:500] if r.text else "No error message"
                    log(f"❌ API_ERROR (retry): Status {r.status_code}, Error: {error_text}")
            else:
                error_text = r.text[:500] if r.text else "No error message"
                log(f"❌ API_ERROR: Status {r.status_code}, Error: {error_text}")
    except Exception as e:
        import traceback
        log(f"❌ EXCEPTION: {str(e)}")
        log(f"💡 TRACEBACK: {traceback.format_exc()[:500]}")
    return None, None

# ───────── BUILD EMAIL HTML ─────────
def build_html(choice, remaining, recipient_email: Optional[str] = None):
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
    
    email_suffix = ""
    if recipient_email:
        email_suffix = f"?email={quote_plus(recipient_email)}"

    next_btn = "".join(
        f'<a href="{FRONTEND_ACTION_BASE}/{choice_to_path(r)}{email_suffix}">{CHOICE_LABELS[r]}</a><br>'
        for r in remaining
    ) if remaining else "<p>We'll follow up soon.</p>"
    return f"""
    <b>{msg['title']}</b><br>{msg['body']}<br><br>
    { f"Choose next: <br>{next_btn}" if remaining else "" }
    """

# ───────── SEND REPLY IN SAME THREAD ─────────
async def reply(eaccount: str, reply_to_uuid: str, subject: str, html: str):
    """Send reply email via Instantly.ai API - uses original email subject to maintain thread"""
    # Use the original subject from the email we're replying to (for thread continuity)
    # Don't modify it - Instantly.ai will handle threading via reply_to_uuid
    # If subject is empty, we shouldn't use a default - we need the actual original subject
    # Use the original subject from the email we're replying to (for thread continuity)
    # For proper email threading, add "Re:" prefix if not already present
    if not subject or not subject.strip():
        log(f"⚠️ REPLY_WARNING: Empty subject provided - this may cause threading issues")
        subject = "Loan Update"  # Fallback only if absolutely necessary
    
    # Add "Re:" prefix for proper threading (but don't add if already present)
    if not subject.lower().startswith("re:"):
        reply_subject = f"Re: {subject}"
    else:
        reply_subject = subject  # Already has "Re:" prefix
    
    async with httpx.AsyncClient(timeout=15) as c:
        reply_json = {
            "eaccount": eaccount,
            "reply_to_uuid": reply_to_uuid,
            "subject": reply_subject,
            "body": {"html": html}
        }
        log(f"📤 REPLY_PAYLOAD: uuid={reply_to_uuid}, subject={reply_subject}, eaccount={eaccount}")
        log(f"💡 REPLY_THREADING: Original subject='{subject}' → Reply subject='{reply_subject}' (for thread continuity)")
        log(f"📤 REPLY_PAYLOAD_FULL: {json.dumps(reply_json, indent=2)[:500]}")
        r = await c.post(INSTANTLY_URL, json=reply_json, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
        
        log(f"📡 REPLY_API_RESPONSE: Status {r.status_code}")
        
        if r.status_code > 299:
            error_response = r.text[:500] if r.text else "No error message"
            log(f"❌ REPLY_API_ERROR: Status {r.status_code}, Response: {error_response}")
            log(f"💡 REPLY_DEBUG: Request payload was: {json.dumps(reply_json, indent=2)[:500]}")
        else:
            response_text = r.text[:500] if r.text else "No response body"
            log(f"✅ REPLY_API_SUCCESS: Status {r.status_code}, Response: {response_text}")
            # Log full response for debugging
            try:
                response_json = r.json()
                log(f"💡 REPLY_RESPONSE_DETAILS: {json.dumps(response_json, indent=2)[:500]}")
            except:
                log(f"💡 REPLY_RESPONSE_TEXT: {response_text}")

# ========== WEBHOOK ==========
app = FastAPI()

# Middleware to log ONLY email click tracking GET requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    host = request.headers.get("host", "unknown")
    client_ip = request.client.host if request.client else "unknown"
    
    # Only log GET requests for email click tracking paths
    if request.method == "GET" and is_email_click_path(request.url.path):
        query_params = dict(request.query_params)
        query_str = "?" + "&".join([f"{k}={v}" for k, v in query_params.items()]) if query_params else ""
        log(f"🌐 EMAIL_CLICK_REQUEST: GET {request.url.path}{query_str} | Host: {host} | Client: {client_ip}")
    
    # Always log webhook requests
    if request.url.path == "/webhook/instantly":
        headers_dict = dict(request.headers)
        log(f"📋 WEBHOOK_HEADERS: {json.dumps(headers_dict, indent=2)}")
    
    response = await call_next(request)
    
    # Only log responses for email click paths
    if request.method == "GET" and is_email_click_path(request.url.path):
        log(f"📤 EMAIL_CLICK_RESPONSE: GET {request.url.path} -> {response.status_code}")
    elif request.url.path == "/webhook/instantly":
        log(f"📤 WEBHOOK_RESPONSE: POST {request.url.path} -> {response.status_code}")
    
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

        matching_click = None
        matching_method = None
        recipient_key = (recipient or "").strip().lower()
        
        log(f"🔍 EMAIL_MATCHING_START: Looking for click for email: {recipient_key}")
        
        # PRIMARY: Email-based matching
        if recipient_key:
            email_click = RECENT_EMAIL_CLICKS.get(recipient_key, None)
            if email_click:
                matching_click = email_click.get("choice")
                email_ts = email_click.get("timestamp")
                age = (datetime.now() - email_ts).total_seconds() if email_ts else 0
                matching_method = "EMAIL_BASED"
                log(f"✅ EMAIL_MATCHING_SUCCESS: Matched via email for {recipient_key} → choice: {matching_click} (age {age:.1f}s)")
                # Don't pop immediately - keep for duplicate webhook handling (TTL will clean it up)
            else:
                log(f"⚠️ EMAIL_MATCHING_FAILED: No stored click found for email {recipient_key}")

        # FALLBACK: Time-based matching
        if not matching_click:
            now = datetime.now()
            for click_time, choice_val, ip in reversed(list(RECENT_CLICKS)):
                time_diff = (now - click_time).total_seconds()
                if time_diff < 60:  # Within last 60 seconds
                    matching_click = choice_val
                    matching_method = "TIME_BASED_FALLBACK"
                    log(f"✅ EMAIL_MATCHING_FALLBACK: Matched via time-based fallback → choice: {choice_val} (from {time_diff:.1f}s ago)")
                    break
            
            if not matching_click:
                log(f"❌ EMAIL_MATCHING_FAILED: No click found for email {recipient_key} (no email match, no time-based fallback)")
        
        if matching_click:
            choice = matching_click
            log(f"📧 EMAIL_MATCHING_COMPLETE: Using choice '{choice}' (matched via {matching_method}) for {recipient_key}")
            
            # Get email_account and campaign_id from webhook payload
            eaccount = payload.get("email_account") or INSTANTLY_EACCOUNT
            campaign_id_val = campaign_id if campaign_id != "unknown" else None
            
            # First, check if webhook payload contains email_id/uuid directly (avoids API rate limits)
            email_uuid = payload.get("email_id") or payload.get("email_uuid") or payload.get("uuid")
            original_subject = payload.get("subject", "Loan Update")
            
            if email_uuid:
                log(f"✅ EMAIL_UUID_FOUND_IN_PAYLOAD: Found email_uuid in webhook payload: {email_uuid}")
            else:
                log(f"🔍 EMAIL_UUID_LOOKUP_START: email_uuid not in payload, trying API lookup...")
                log(f"🔍 EMAIL_UUID_LOOKUP_START: recipient={recipient_key}, eaccount={eaccount}, campaign_id={campaign_id_val}")
                log(f"💡 DEBUG: Full payload email_account='{payload.get('email_account')}', campaign_id='{campaign_id}'")
                
                # Get email uuid and subject from Instantly.ai API (only if not in payload)
                email_uuid, original_subject = await find_email_uuid_for_lead(eaccount, recipient, campaign_id_val)
            
            log(f"🔍 EMAIL_UUID_LOOKUP_RESULT: uuid={email_uuid}, subject={original_subject}")
            
            if email_uuid:
                # Get remaining choices
                remaining = [c for c in ALL if c != choice]
                html = build_html(choice, remaining, recipient)
                await reply(eaccount, email_uuid, original_subject, html)
                log(f"✅ REPLY_SENT: Automatic reply sent for choice '{choice}' to {recipient_key} (matched via {matching_method})")
            else:
                log(f"❌ REPLY_FAILED: Could not find email uuid for {recipient_key}. Reply not sent.")
                log(f"💡 DEBUG: Webhook payload email_account='{payload.get('email_account')}', campaign_id='{campaign_id}', recipient='{recipient}'")
                log(f"💡 DEBUG: Using eaccount='{eaccount}', campaign_id_val='{campaign_id_val}'")
        else:
            log(f"❌ EMAIL_MATCHING_NO_RESULT: No matching click found for webhook from {recipient_key}")
    
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

@app.get("/logs/get-requests")
def logs_get_requests():
    """Filter logs to show only email click tracking GET requests and webhook events"""
    # Only show email click tracking requests, webhook events, and related events
    email_logs = [
        log for log in LOGS 
        if any(keyword in log.get("m", "") for keyword in [
            "EMAIL_CLICK_REQUEST",
            "EMAIL_CLICK_RESPONSE", 
            "LINK_CLICKED",
            "EMAIL_MATCHING",
            "EMAIL_STORED",
            "Stored choice",
            "Matched",
            "REPLY_SENT",
            "REPLY_FAILED",
            "WEBHOOK",
            "EMAIL_ID",
            "EMAIL_UUID",
            "UUID",
            "API_CALL",
            "API_RESPONSE",
            "API_RESULT",
            "API_ERROR",
            "EMAIL_CLICK_STORED",
            "EMAIL_CLICK_WAITING",
            "DEBUG"
        ])
    ]
    return list(email_logs[-100:])  # Last 100 email-related logs

@app.get("/logs/live")
def logs_live_html():
    """Live log viewer page that auto-refreshes - shows GET requests only"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live GET Request Logs - Production Tracking</title>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                background: #1e1e1e;
                color: #d4d4d4;
                margin: 0;
                padding: 20px;
            }
            .header {
                background: #2d2d30;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                position: sticky;
                top: 0;
                z-index: 100;
            }
            .header h1 {
                margin: 0;
                color: #4ec9b0;
            }
            .header p {
                margin: 5px 0 0 0;
                color: #858585;
                font-size: 12px;
            }
            .log-container {
                background: #252526;
                border-radius: 5px;
                padding: 15px;
                max-height: 80vh;
                overflow-y: auto;
            }
            .log-entry {
                padding: 8px;
                margin: 5px 0;
                border-left: 3px solid #007acc;
                background: #1e1e1e;
                border-radius: 3px;
                word-wrap: break-word;
            }
            .log-time {
                color: #858585;
                font-size: 11px;
            }
            .log-message {
                color: #d4d4d4;
                margin-top: 5px;
            }
            .log-message:contains("LINK_CLICKED") {
                color: #4ec9b0;
            }
            .refresh-indicator {
                display: inline-block;
                width: 10px;
                height: 10px;
                background: #0f0;
                border-radius: 50%;
                animation: blink 2s infinite;
            }
            @keyframes blink {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
            }
            .stats {
                display: inline-block;
                margin-left: 20px;
                color: #858585;
            }
            .click-highlight {
                background: #2a4a2a !important;
                border-left-color: #4ec9b0 !important;
            }
            .click-highlight .log-message {
                color: #4ec9b0;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 Live GET Request Tracker <span class="refresh-indicator"></span></h1>
            <p>Auto-refreshing every 2 seconds • Showing GET requests only • Production monitoring</p>
        </div>
        <div class="log-container" id="logs">
            <p style="color: #858585;">Loading logs...</p>
        </div>
        
        <script>
            let lastLogCount = 0;
            let loadedLogs = new Set(); // Track loaded log entries to avoid duplicates
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            function createLogEntry(log) {
                const isClick = log.m && (log.m.includes('LINK_CLICKED') || log.m.includes('Stored choice') || log.m.includes('EMAIL_MATCHING') || log.m.includes('REPLY_SENT'));
                const logClass = isClick ? 'log-entry click-highlight' : 'log-entry';
                const logId = `${log.t || Date.now()}_${log.m ? log.m.substring(0, 50) : ''}`;
                
                return {
                    id: logId,
                    html: `
                        <div class="${logClass}" data-log-id="${logId}">
                            <div class="log-time">${log.t || ''}</div>
                            <div class="log-message">${escapeHtml(log.m || '')}</div>
                        </div>
                    `
                };
            }
            
            async function appendNewLogs() {
                try {
                    const response = await fetch('/logs/get-requests');
                    const logs = await response.json();
                    const container = document.getElementById('logs');
                    
                    if (logs.length === 0 && lastLogCount === 0) {
                        container.innerHTML = '<p style="color: #858585;">No logs yet. Waiting for activity...</p>';
                        return;
                    }
                    
                    // Only process new logs
                    if (logs.length > lastLogCount) {
                        const newLogs = logs.slice(lastLogCount);
                        
                        newLogs.reverse().forEach(log => {
                            const entry = createLogEntry(log);
                            if (!loadedLogs.has(entry.id)) {
                                loadedLogs.add(entry.id);
                                container.insertAdjacentHTML('afterbegin', entry.html);
                            }
                        });
                        
                        lastLogCount = logs.length;
                        
                        // Keep only last 100 entries visible
                        const allEntries = container.querySelectorAll('.log-entry');
                        if (allEntries.length > 100) {
                            for (let i = 100; i < allEntries.length; i++) {
                                const logId = allEntries[i].getAttribute('data-log-id');
                                loadedLogs.delete(logId);
                                allEntries[i].remove();
                            }
                        }
                    }
                } catch (error) {
                    console.error('Error loading logs:', error);
                }
            }
            
            // Initial load
            async function initialLoad() {
                try {
                    const response = await fetch('/logs/get-requests');
                    const logs = await response.json();
                    const container = document.getElementById('logs');
                    
                    if (logs.length === 0) {
                        container.innerHTML = '<p style="color: #858585;">No logs yet. Waiting for activity...</p>';
                        return;
                    }
                    
                    // Load last 50 entries initially
                    const initialLogs = logs.slice(-50).reverse();
                    let html = '';
                    
                    initialLogs.forEach(log => {
                        const entry = createLogEntry(log);
                        if (!loadedLogs.has(entry.id)) {
                            loadedLogs.add(entry.id);
                            html += entry.html;
                        }
                    });
                    
                    container.innerHTML = html;
                    lastLogCount = logs.length;
                } catch (error) {
                    document.getElementById('logs').innerHTML = `<p style="color: #f48771;">Error loading logs: ${error.message}</p>`;
                }
            }
            
            // Initial load
            initialLoad();
            
            // Append new logs every 2 seconds (no full refresh)
            setInterval(appendNewLogs, 2000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)

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
        <a href="{FRONTEND_ACTION_BASE}/close?email=test@example.com" target="_blank">🔵 Close my loan</a><br><br>
        <a href="{FRONTEND_ACTION_BASE}/settle?email=test@example.com" target="_blank">💠 Settle my loan</a><br><br>
        <a href="{FRONTEND_ACTION_BASE}/never?email=test@example.com" target="_blank">⚠️ I will never pay</a><br><br>
        <a href="{FRONTEND_ACTION_BASE}/human?email=test@example.com" target="_blank">⏳ Need more time</a><br><br>
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
    # Skip favicon and other non-email paths silently - return immediately without logging
    skip_paths = {"favicon.ico", "robots.txt", ".well-known"}
    path_lower = path_choice.lower()
    if path_lower in skip_paths or any(path_lower.startswith(skip) for skip in skip_paths):
        return PlainTextResponse("", status_code=204)  # Silent ignore - no logging
    
    client_ip = request.client.host if request.client else "unknown"
    
    # Map path to choice
    choice = PATH_TO_CHOICE.get(path_lower, "unknown")
    
    # Only log and process if it's a valid email click path
    if choice != "unknown":
        log(f"🔗 LINK_CLICKED: /{path_choice} → choice: {choice} | IP: {client_ip}")

        query_params = dict(request.query_params)
        email_param = (
            query_params.get("email")
            or query_params.get("lead_email")
            or query_params.get("recipient")
        )
        
        # Store the click with timestamp - webhook will match within 60 seconds
        if email_param:
            store_email_click(email_param, choice, client_ip)
            log(f"💾 EMAIL_CLICK_STORED: Choice '{choice}' stored for email '{email_param}' - ready for email-based matching")
        else:
            log(f"⚠️ EMAIL_CLICK_NO_EMAIL: Choice '{choice}' stored without email parameter - will use time-based fallback")
        RECENT_CLICKS.append((datetime.now(), choice, client_ip))
        log(f"⏳ EMAIL_CLICK_WAITING: Waiting for Instantly.ai webhook to trigger automatic reply")
    # Don't log unknown paths - just return silently
    
    return PlainTextResponse("",status_code=204)  # invisible

