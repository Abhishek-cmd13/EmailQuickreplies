import os
import logging
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from collections import deque

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ─────────────────────────────
# ENV
# ─────────────────────────────
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
INSTANTLY_EACCOUNT = os.getenv("INSTANTLY_EACCOUNT")  # e.g. collections@riverline.ai
FRONTEND_ACTION_BASE = os.getenv(
    "FRONTEND_ACTION_BASE",
    "https://riverline.ai/qr"  # just needs to be a URL Instantly can track
)

# Campaign ID restriction - only process events from this campaign
ALLOWED_CAMPAIGN_ID = "e205ce46-f772-42fd-a81c-40eaa996f54e"

if not INSTANTLY_API_KEY or not INSTANTLY_EACCOUNT:
    raise RuntimeError("Set INSTANTLY_API_KEY and INSTANTLY_EACCOUNT in env")

INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"

# ─────────────────────────────
# LOGGING
# ─────────────────────────────
# Log buffer to store recent log entries
LOG_BUFFER = deque(maxlen=1000)  # Keep last 1000 log entries

class LogBufferHandler(logging.Handler):
    """Custom logging handler that stores logs in a buffer"""
    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "level": record.levelname,
                "message": self.format(record)
            }
            LOG_BUFFER.append(log_entry)
        except Exception:
            pass  # Don't fail if logging fails

# Setup logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True  # Force reconfiguration
)
log = logging.getLogger("webhook-reply-backend")

# Add buffer handler to capture logs
buffer_handler = LogBufferHandler()
buffer_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
buffer_handler.setLevel(logging.DEBUG)  # Capture all log levels

# Add to our logger
log.addHandler(buffer_handler)
log.setLevel(logging.DEBUG)

# Add to root logger to catch all logs from any module
root_logger = logging.getLogger()
root_logger.addHandler(buffer_handler)
root_logger.setLevel(logging.DEBUG)

# Log buffer is ready (don't log initialization to keep logs clean)

# ─────────────────────────────
# OPTIONS / LABELS
# ─────────────────────────────
CHOICE_LABELS: Dict[str, str] = {
    "close_loan": "🔵 Close my loan",
    "settle_loan": "💠 Settle my loan",
    "never_pay": "⚠️ I will never pay this loan",
    "need_more_time": "⏳ I need more time",
}

ALL_CHOICES: List[str] = list(CHOICE_LABELS.keys())

# Optional: choice → explanation + next-steps text
CHOICE_COPY: Dict[str, Dict[str, str]] = {
    "close_loan": {
        "title": "You'd like to close your loan",
        "body": "Thanks for letting us know you want to close your loan. We'll share closure steps and final amount shortly.",
    },
    "settle_loan": {
        "title": "You're exploring a settlement",
        "body": "Thanks for choosing settlement. We'll evaluate your account and share a settlement proposal.",
    },
    "never_pay": {
        "title": "You're unable / unwilling to pay",
        "body": "We understand circumstances can be difficult. We'll review your case and see what support or options are possible.",
    },
    "need_more_time": {
        "title": "You need more time",
        "body": "We've noted that you need more time. We'll get back with flexible date/options to help you.",
    },
}


# ─────────────────────────────
# APP
# ─────────────────────────────
app = FastAPI(
    title="Riverline – Instantly Webhook Reply Backend",
    version="1.0.0",
)


# ─────────────────────────────
# Helpers
# ─────────────────────────────

def extract_choice_from_link(link: str) -> Optional[str]:
    """
    We expect links like:
      https://riverline.ai/qr?c=close_loan
      https://riverline.ai/qr?choice=settle_loan

    We only care about query param c/choice.
    """
    from urllib.parse import urlparse, parse_qs

    try:
        parsed = urlparse(link)
        qs = parse_qs(parsed.query)
        choice = qs.get("c") or qs.get("choice")
        if choice:
            return choice[0]
    except Exception as e:
        log.warning(f"Failed to parse choice from link={link}: {e}")
    return None


async def send_reply_same_thread(
    email_uuid: str,
    subject: Optional[str],
    html_body: str,
) -> Dict[str, Any]:
    """
    Use Instantly reply API to send a threaded email.

    reply_to_uuid: email_id from webhook → keeps it in same thread.
    """
    # Normalise subject
    subj = subject or "Update about your loan"
    subj = subj.strip()
    if not subj.lower().startswith("re:"):
        subj = f"Re: {subj}"

    payload = {
        "reply_to_uuid": email_uuid,
        "eaccount": INSTANTLY_EACCOUNT,
        "subject": subj,
        "body": {"html": html_body},
    }

    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json",
    }

    log.info(f"Sending reply via Instantly: email_uuid={email_uuid}, subject={subj}")

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{INSTANTLY_BASE_URL}/emails/reply", json=payload, headers=headers
        )

    if resp.status_code >= 400:
        log.error(f"Instantly reply error {resp.status_code}: {resp.text}")
        raise HTTPException(
            status_code=500,
            detail=f"Instantly reply failed: {resp.status_code}",
        )

    return resp.json()


def build_buttons_html(remaining_choices: List[str]) -> str:
    """
    Only purpose of URLs is: Instantly will track click and call our webhook again.

    We DO NOT need to host GET pages at FRONTEND_ACTION_BASE.
    If you want, you can serve a simple 'Thanks' page separately.
    """
    if not remaining_choices:
        return ""

    button_style = (
        "display:block;"
        "margin:8px 0;"
        "padding:10px 14px;"
        "background:#4a3aff;"
        "color:#ffffff;"
        "text-decoration:none;"
        "border-radius:6px;"
        "font-family:system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
        "font-size:14px;"
        "text-align:center;"
    )

    parts = []
    for key in remaining_choices:
        label = CHOICE_LABELS.get(key, key)
        url = f"{FRONTEND_ACTION_BASE}?c={key}"
        parts.append(f'<a href="{url}" style="{button_style}">{label}</a>')

    return "<br>".join(parts)


def build_email_html(chosen: str, remaining: List[str]) -> str:
    copy = CHOICE_COPY.get(
        chosen,
        {
            "title": "Thank you for your response",
            "body": "We've recorded your selection.",
        },
    )

    buttons_html = build_buttons_html(remaining)

    extra_block = ""
    if remaining:
        extra_block = f"""
        <p style="font-weight:600; margin-top:24px;">
            To help us understand better, please choose one more option:
        </p>
        <div>{buttons_html}</div>
        """

    html = f"""
    <html>
      <body style="font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6;color:#111827;background:#f9fafb;padding:24px;">
        <div style="max-width:600px;margin:0 auto;background:white;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
          <h2 style="color:#4a3aff;margin-top:0;margin-bottom:12px;">{copy['title']}</h2>
          <p style="margin:0 0 18px 0;">{copy['body']}</p>

          {extra_block if remaining else ""}

          {"<p style='font-size:12px;color:#6b7280;margin-top:24px;'>We'll be in touch shortly with next steps.</p>" if not remaining else ""}

          <p style="font-size:12px;color:#9ca3af;margin-top:24px;border-top:1px solid #e5e7eb;padding-top:12px;">
            This is an automated email. You can reply to this email if anything is unclear.
          </p>
        </div>
      </body>
    </html>
    """
    return html


def detect_event_type(payload: Dict[str, Any]) -> str:
    """
    Try to infer event type from various keys.
    Instantly may send: "event", "type", "event_type", etc.
    """
    return (
        payload.get("event")
        or payload.get("type")
        or payload.get("event_type")
        or ""
    )


def get_email_uuid(payload: Dict[str, Any]) -> Optional[str]:
    """
    Try to extract the email UUID used by Instantly for replies.
    """
    return (
        payload.get("email_id")
        or payload.get("email_uuid")
        or payload.get("id")
        or payload.get("emailId")
    )


def get_clicked_link(payload: Dict[str, Any]) -> Optional[str]:
    """
    Try to extract the clicked URL from various possible fields.
    """
    return (
        payload.get("link")
        or payload.get("url")
        or payload.get("clicked_url")
        or payload.get("clickedLink")
    )


def get_campaign_id(payload: Dict[str, Any]) -> Optional[str]:
    """
    Try to extract the campaign ID from various possible fields.
    """
    return (
        payload.get("campaign_id")
        or payload.get("campaignId")
        or payload.get("campaign_uuid")
        or payload.get("campaign")
    )


# ─────────────────────────────
# Middleware to log ALL incoming requests
# ─────────────────────────────
@app.middleware("http")
async def log_all_requests(request: Request, call_next):
    """Log ALL POST requests to catch webhooks that might not match our endpoint"""
    from datetime import datetime
    start_time = datetime.now()
    
    # Log ALL POST requests to catch any webhook attempts
    is_post_request = request.method == "POST"
    
    if is_post_request:
        log.info("=" * 80)
        log.info(f"🌐 INCOMING POST REQUEST: {request.method} {request.url.path}")
        log.info(f"   Full URL: {request.url}")
        log.info(f"   Client: {request.client.host if request.client else 'unknown'}")
        log.info(f"   User-Agent: {request.headers.get('user-agent', 'N/A')}")
        log.info(f"   Content-Type: {request.headers.get('content-type', 'N/A')}")
        log.info(f"   Content-Length: {request.headers.get('content-length', 'N/A')}")
        log.info("=" * 80)
    
    try:
        response = await call_next(request)
        if is_post_request:
            process_time = (datetime.now() - start_time).total_seconds()
            log.info(f"✅ POST REQUEST COMPLETED: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
        return response
    except Exception as e:
        if is_post_request:
            log.error(f"❌ POST REQUEST ERROR: {request.method} {request.url.path} - {str(e)}")
            import traceback
            log.error(traceback.format_exc())
        raise


# ─────────────────────────────
# Routes
# ─────────────────────────────

@app.get("/health")
async def health():
    # Don't log health checks to avoid clutter in webhook logs
    return {
        "status": "ok",
        "instantly_configured": bool(INSTANTLY_API_KEY and INSTANTLY_EACCOUNT),
        "frontend_action_base": FRONTEND_ACTION_BASE,
        "allowed_campaign_id": ALLOWED_CAMPAIGN_ID,
        "log_buffer_size": len(LOG_BUFFER),
    }


@app.get("/logs", response_class=HTMLResponse)
async def view_logs():
    """HTML page to view logs with auto-refresh"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Logs - Webhook Backend</title>
        <style>
            body {
                font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                background: #1e1e1e;
                color: #d4d4d4;
                margin: 0;
                padding: 20px;
            }
            h1 {
                color: #4a9eff;
                border-bottom: 2px solid #4a9eff;
                padding-bottom: 10px;
            }
            #log-container {
                background: #252526;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 15px;
                max-height: 80vh;
                overflow-y: auto;
                white-space: pre-wrap;
                font-size: 13px;
                line-height: 1.5;
            }
            .log-entry {
                margin: 2px 0;
                padding: 2px 0;
            }
            .log-info { color: #4a9eff; }
            .log-warning { color: #ffa500; }
            .log-error { color: #f48771; }
            .log-success { color: #89d185; }
            .controls {
                margin: 15px 0;
                display: flex;
                gap: 10px;
                align-items: center;
            }
            button {
                background: #4a9eff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            button:hover { background: #3a8eef; }
            button:disabled { background: #555; cursor: not-allowed; }
            #status {
                color: #89d185;
                font-weight: bold;
            }
            .timestamp { color: #858585; }
        </style>
    </head>
    <body>
        <h1>📋 Live Logs Viewer</h1>
        <div class="controls">
            <button id="refreshBtn" onclick="refreshLogs()">🔄 Refresh</button>
            <button id="clearBtn" onclick="clearLogs()">🗑️ Clear</button>
            <button id="autoRefreshBtn" onclick="toggleAutoRefresh()">⏸️ Auto-refresh</button>
            <button onclick="fetch('/test/webhook', {method: 'POST'}).then(() => refreshLogs())">🧪 Test Webhook</button>
            <span id="status">● Live</span>
            <span style="color: #858585;">| Last updated: <span id="lastUpdate">-</span></span>
        </div>
        <div id="log-container"></div>
        <script>
            let autoRefreshInterval = null;
            let isAutoRefreshing = false;

            function formatLog(logEntry) {
                const level = logEntry.level.toLowerCase();
                const timestamp = logEntry.timestamp ? new Date(logEntry.timestamp).toLocaleTimeString() : '';
                const levelClass = `log-${level}`;
                return `<div class="log-entry ${levelClass}"><span class="timestamp">[${timestamp}]</span> ${escapeHtml(logEntry.message)}</div>`;
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            async function refreshLogs() {
                try {
                    // Server now filters to only webhook-related logs
                    const response = await fetch('/logs/json?limit=500');
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const logs = await response.json();
                    const container = document.getElementById('log-container');
                    
                    if (!Array.isArray(logs)) {
                        container.innerHTML = '<div style="color: #f48771;">Error: Invalid response format</div>';
                        return;
                    }
                    
                    if (logs.length === 0) {
                        container.innerHTML = '<div style="color: #858585;">No webhook logs yet.<br>Waiting for webhooks from Instantly.ai...<br><br>When a webhook arrives, you\'ll see:<br>- Full request headers and payload<br>- Campaign ID validation<br>- Event processing<br>- Reply sending status</div>';
                        return;
                    }
                    
                    container.innerHTML = logs.map(formatLog).join('');
                    container.scrollTop = container.scrollHeight;
                    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
                } catch (error) {
                    console.error('Error fetching logs:', error);
                    const container = document.getElementById('log-container');
                    container.innerHTML = `<div style="color: #f48771;">Error loading logs: ${error.message}</div>`;
                }
            }

            function clearLogs() {
                fetch('/logs/clear', { method: 'POST' });
                document.getElementById('log-container').innerHTML = '';
            }

            function toggleAutoRefresh() {
                const btn = document.getElementById('autoRefreshBtn');
                if (isAutoRefreshing) {
                    clearInterval(autoRefreshInterval);
                    btn.textContent = '▶️ Auto-refresh';
                    btn.style.background = '#4a9eff';
                    isAutoRefreshing = false;
                    document.getElementById('status').textContent = '● Paused';
                } else {
                    autoRefreshInterval = setInterval(refreshLogs, 1000);
                    btn.textContent = '⏸️ Auto-refresh';
                    btn.style.background = '#89d185';
                    isAutoRefreshing = true;
                    document.getElementById('status').textContent = '● Live';
                }
            }

            // Initial load and start auto-refresh
            refreshLogs();
            toggleAutoRefresh();
        </script>
    </body>
    </html>
    """


@app.get("/logs/json")
async def get_logs_json(limit: int = 500):
    """Get logs as JSON - only webhook-related logs"""
    logs = list(LOG_BUFFER)
    
    # Filter to only show webhook-related logs
    webhook_keywords = [
        "WEBHOOK",
        "📥",
        "INCOMING WEBHOOK",
        "INCOMING POST REQUEST",
        "POST REQUEST",
        "INCOMING REQUEST: POST",
        "WEBHOOK ENDPOINT HIT",
        "CAMPAIGN ID",
        "EVENT TYPE",
        "EXTRACTED DATA",
        "REJECTED",
        "VALIDATED",
        "PROCESSING",
        "SENDING REPLY",
        "REPLY SENT",
        "click event",
        "email_uuid",
        "clicked_link",
        "choice",
        "remaining_choices",
        "/webhook"
    ]
    
    # Only keep logs that contain webhook-related keywords
    filtered_logs = []
    for log_entry in logs:
        message = log_entry.get("message", "")
        if any(keyword in message for keyword in webhook_keywords):
            filtered_logs.append(log_entry)
    
    # Apply limit
    if limit:
        filtered_logs = filtered_logs[-limit:]
    
    return filtered_logs


@app.post("/logs/clear")
async def clear_logs():
    """Clear the log buffer"""
    LOG_BUFFER.clear()
    # Don't log the clear action to avoid clutter
    return {"status": "ok", "message": "Log buffer cleared"}


@app.post("/test/webhook")
async def test_webhook():
    """Test endpoint to simulate a webhook and generate logs"""
    log.info("=" * 80)
    log.info("🧪 TEST WEBHOOK TRIGGERED")
    log.info("=" * 80)
    log.info("This is a test webhook to verify logging is working")
    log.info("When real webhooks come in, you'll see similar logs")
    log.info("=" * 80)
    return {
        "status": "ok",
        "message": "Test webhook logged. Check /logs to see the entries.",
        "log_buffer_size": len(LOG_BUFFER)
    }


@app.get("/webhook-status")
async def webhook_status():
    """Diagnostic endpoint to check webhook configuration"""
    total_logs = len(LOG_BUFFER)
    
    # Find all POST request logs
    post_logs = [log for log in LOG_BUFFER if "POST REQUEST" in log.get("message", "").upper()]
    webhook_endpoint_logs = [log for log in LOG_BUFFER if "/webhook" in log.get("message", "") or "WEBHOOK ENDPOINT" in log.get("message", "").upper()]
    
    return {
        "status": "ok",
        "webhook_endpoint_url": "https://emailquickreplies.onrender.com/webhook/instantly",
        "total_logs_in_buffer": total_logs,
        "total_post_requests": len(post_logs),
        "webhook_endpoint_hits": len(webhook_endpoint_logs),
        "recent_post_requests": post_logs[-5:] if post_logs else [],
        "recent_webhook_logs": webhook_endpoint_logs[-5:] if webhook_endpoint_logs else [],
        "diagnosis": "If total_post_requests is 0, Instantly.ai is not sending webhooks to your server. Check Instantly.ai dashboard → Webhooks → Ensure URL is set correctly.",
        "checklist": [
            "1. Go to Instantly.ai Dashboard → Settings → Webhooks",
            "2. Verify webhook URL is: https://emailquickreplies.onrender.com/webhook/instantly",
            "3. Ensure CLICK events are enabled",
            "4. Remove Slack webhook if you only want your app to receive webhooks",
            "5. Save and test by clicking a button in an email"
        ]
    }


@app.api_route("/webhook/instantly", methods=["POST", "GET", "PUT", "DELETE"])
@app.api_route("/webhook/instantly/", methods=["POST", "GET", "PUT", "DELETE"])
@app.api_route("/webhook", methods=["POST", "GET", "PUT", "DELETE"])
async def instantly_webhook(request: Request):
    """
    Main webhook endpoint.

    Configure in Instantly dashboard:
      URL: https://your-backend.onrender.com/webhook/instantly
      Events: CLICK (and optionally SENT/OPEN for future use)

    Expected (approx) click payload:
    {
      "event": "click",
      "email_id": "uuid-here",
      "recipient": "user@example.com",
      "link": "https://riverline.ai/qr?c=close_loan",
      "subject": "Loan update",
      "campaign_id": "e205ce46-f772-42fd-a81c-40eaa996f54e",
      ...
    }
    """
    import json
    from datetime import datetime
    
    # CRITICAL: Log ALL webhooks FIRST, before any validation
    # This ensures we capture everything, even invalid requests
    
    # Get raw body for logging
    try:
        body = await request.body()
    except Exception as e:
        body = b""
        log.error(f"Failed to read request body: {e}")
    
    # Log complete incoming request - THIS HAPPENS FOR ALL WEBHOOKS
    log.info("=" * 80)
    log.info(f"📥 INCOMING WEBHOOK REQUEST - {datetime.now().isoformat()}")
    log.info("=" * 80)
    log.info(f"Headers: {dict(request.headers)}")
    log.info(f"Method: {request.method}")
    log.info(f"URL: {request.url}")
    log.info(f"Client: {request.client.host if request.client else 'unknown'}")
    log.info("-" * 80)
    log.info("RAW BODY:")
    try:
        body_json = json.loads(body) if body else {}
        log.info(json.dumps(body_json, indent=2))
    except Exception as e:
        log.warning(f"Failed to parse body as JSON: {e}")
        log.info(body.decode('utf-8', errors='ignore') if body else "(empty body)")
    log.info("=" * 80)

    # Parse payload - handle errors gracefully
    try:
        # If we already parsed it, use that, otherwise parse again
        if 'body_json' in locals():
            payload = body_json
        else:
            payload = await request.json()
        
        # Log parsed payload
        log.info("PARSED PAYLOAD:")
        log.info(json.dumps(payload, indent=2))
    except Exception as e:
        log.error(f"Failed to parse request as JSON: {e}")
        log.info("Proceeding with empty payload for validation")
        payload = {}

    # Validate campaign ID - only process events from allowed campaign
    campaign_id = get_campaign_id(payload)
    
    log.info("-" * 80)
    log.info("CAMPAIGN ID VALIDATION:")
    log.info(f"  Received campaign_id: {campaign_id}")
    log.info(f"  Allowed campaign_id: {ALLOWED_CAMPAIGN_ID}")
    
    if not campaign_id:
        log.warning("❌ REJECTED: campaign_id missing from payload")
        log.info("=" * 80)
        log.info("✅ WEBHOOK LOGGED (rejected but logged for debugging)")
        log.info("=" * 80)
        return JSONResponse({
            "status": "ignored",
            "reason": "missing_campaign_id",
            "allowed_campaign_id": ALLOWED_CAMPAIGN_ID,
            "message": "Webhook must include campaign_id. This system is restricted to a single campaign."
        })
    
    if campaign_id != ALLOWED_CAMPAIGN_ID:
        log.warning(f"❌ REJECTED: campaign_id {campaign_id} does not match allowed campaign")
        log.info("=" * 80)
        log.info("✅ WEBHOOK LOGGED (rejected but logged for debugging)")
        log.info("=" * 80)
        return JSONResponse({
            "status": "ignored",
            "reason": "wrong_campaign_id",
            "received_campaign_id": campaign_id,
            "allowed_campaign_id": ALLOWED_CAMPAIGN_ID,
            "message": f"This system only processes events from campaign {ALLOWED_CAMPAIGN_ID}"
        })
    
    log.info(f"✅ Campaign ID validated: {campaign_id}")

    event_type = detect_event_type(payload)
    
    log.info("-" * 80)
    log.info("EVENT TYPE:")
    log.info(f"  Detected event_type: {event_type}")
    
    if not event_type:
        log.warning("❌ REJECTED: Webhook without event type")
        log.info("=" * 80)
        log.info("✅ WEBHOOK LOGGED (rejected but logged for debugging)")
        log.info("=" * 80)
        return JSONResponse({"status": "ignored", "reason": "no_event_type"})

    # We only care about click events for this flow
    if "click" not in event_type.lower():
        log.info(f"⚠️  IGNORED: Event type '{event_type}' is not a click event")
        log.info("=" * 80)
        log.info("✅ WEBHOOK LOGGED (ignored but logged for debugging)")
        log.info("=" * 80)
        return JSONResponse({"status": "ignored", "event_type": event_type})
    
    log.info(f"✅ Processing click event")

    email_uuid = get_email_uuid(payload)
    clicked_link = get_clicked_link(payload)
    subject = payload.get("subject") or payload.get("email_subject")

    log.info("-" * 80)
    log.info("EXTRACTED DATA:")
    log.info(f"  email_uuid: {email_uuid}")
    log.info(f"  clicked_link: {clicked_link}")
    log.info(f"  subject: {subject}")

    if not email_uuid:
        log.error("❌ ERROR: Click webhook missing email_uuid")
        log.info("=" * 80)
        raise HTTPException(status_code=400, detail="Missing email_id/email_uuid in payload")

    if not clicked_link:
        log.error("❌ ERROR: Click webhook missing link/url")
        log.info("=" * 80)
        raise HTTPException(status_code=400, detail="Missing link/url in payload")

    choice = extract_choice_from_link(clicked_link)
    log.info(f"  Extracted choice: {choice}")
    
    if not choice:
        log.warning(f"❌ REJECTED: Could not parse choice from link={clicked_link}")
        log.info("=" * 80)
        return JSONResponse({"status": "ignored", "reason": "no_choice_in_link"})

    if choice not in ALL_CHOICES:
        log.warning(f"❌ REJECTED: Unknown choice '{choice}', allowed={ALL_CHOICES}")
        log.info("=" * 80)
        return JSONResponse({"status": "ignored", "reason": f"unknown_choice_{choice}"})

    log.info(f"✅ Valid choice: {choice}")

    # Stateless forward logic: remaining = ALL - current choice
    remaining = [c for c in ALL_CHOICES if c != choice]
    log.info(f"  Remaining choices: {remaining}")
    
    log.info("-" * 80)
    log.info("BUILDING REPLY EMAIL...")
    html_body = build_email_html(choice, remaining)

    log.info("-" * 80)
    log.info("SENDING REPLY VIA INSTANTLY.AI...")
    await send_reply_same_thread(email_uuid, subject, html_body)

    log.info("=" * 80)
    log.info("✅ WEBHOOK PROCESSED SUCCESSFULLY")
    log.info(f"   Choice: {choice}")
    log.info(f"   Email UUID: {email_uuid}")
    log.info(f"   Remaining choices: {remaining}")
    log.info("=" * 80)

    return JSONResponse(
        {
            "status": "ok",
            "handled_event": "click",
            "choice": choice,
            "remaining_choices": remaining,
            "email_uuid": email_uuid,
        }
    )

