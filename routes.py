"""FastAPI route handlers"""
import json
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from fastapi import Request, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, RedirectResponse

from config import (
    BACKEND_BASE_URL, FRONTEND_ACTION_BASE, INSTANTLY_EACCOUNT,
    PATH_TO_CHOICE
)
from storage import LOGS
from logger import log
from email_service import store_email_click
from webhook_handler import process_webhook_logic


def register_routes(app):
    """Register all routes with the FastAPI app"""
    
    @app.post("/webhook/instantly")
    async def instantly_webhook(req: Request, bg: BackgroundTasks):
        """Fast webhook endpoint - returns immediately, processes in background"""
        print("🔥🔥 WEBHOOK HIT — REQUEST RECEIVED 🔥🔥")
        client_ip = req.client.host if req.client else "unknown"
        host = req.headers.get("host", "unknown")
        log(f"🔔 WEBHOOK_ENDPOINT_CALLED: POST /webhook/instantly | Host: {host} | IP: {client_ip}")
        
        try:
            payload = await req.json()
            log(f"📥 WEBHOOK_PAYLOAD_RECEIVED: {json.dumps(payload, indent=2)}")
            
            event_type = payload.get("event_type") or payload.get("event") or payload.get("type") or "unknown"
            recipient = payload.get("lead_email") or payload.get("email") or payload.get("recipient") or "unknown"
            campaign_id = payload.get("campaign_id", "unknown")
            email_account = payload.get("email_account", "unknown")
            
            log(f"📋 WEBHOOK_EVENT_TYPE: {event_type}")
            log(f"👤 WEBHOOK_LEAD_EMAIL: {recipient}")
            log(f"📧 WEBHOOK_EMAIL_ACCOUNT: {email_account}")
            log(f"🆔 WEBHOOK_CAMPAIGN_ID: {campaign_id}")
            log(f"⚡ WEBHOOK_RECEIVED: {event_type} for {recipient} - queuing for background processing")
            
        except Exception as e:
            body = await req.body()
            body_str = body.decode('utf-8', errors='ignore')[:200] if body else "(empty)"
            log(f"❌ WEBHOOK_INVALID_JSON: {str(e)} body={body_str[:100]}")
            log(f"❌ WEBHOOK_PROCESSING_ERROR: Failed to parse webhook payload - {str(e)}")
            return {"ok": True, "error": "invalid_json"}
        
        if not payload:
            log(f"⚠️ WEBHOOK_EMPTY_PAYLOAD")
            return {"ok": True, "error": "empty_payload"}
        
        bg.add_task(process_webhook_logic, payload)
        log(f"✅ WEBHOOK_ACCEPTED: Webhook queued for background processing, returning 200 OK")
        return {"ok": True, "status": "accepted", "message": "webhook received and queued for processing"}

    @app.get("/lt/{tracking_path:path}")
    async def handle_instantly_tracking(tracking_path: str, request: Request):
        """Handle Instantly.ai tracking redirects"""
        log(f"🔀 Instantly.ai tracking: /lt/{tracking_path}")
        log(f"   Query params: {dict(request.query_params)}")
        log(f"   Full URL: {request.url}")
        
        query_params = dict(request.query_params)
        destination = query_params.get("url") or query_params.get("destination") or query_params.get("redirect")
        
        if destination:
            log(f"📍 Found destination in params: {destination}")
            parsed = urlparse(destination)
            choice_params = parse_qs(parsed.query)
            choice = choice_params.get("c", choice_params.get("choice", [None]))[0] or "unknown"
            
            if choice != "unknown":
                log(f"💾 Tracking redirect: Choice {choice} detected (email-based matching required)")
            
            return RedirectResponse(url=destination, status_code=302)
        
        log(f"⚠️ No destination found in tracking URL - Instantly.ai should redirect automatically")
        return PlainTextResponse("", status_code=204)

    @app.get("/qr")
    async def qr_click(request: Request):
        """Legacy query param endpoint"""
        query_params = dict(request.query_params)
        choice = query_params.get("c") or query_params.get("choice") or "unknown"
        client_ip = request.client.host if request.client else "unknown"
        
        log(f"🔗 LINK_CLICKED (legacy): /qr?c={choice} | Params: {query_params} | IP: {client_ip}")
        
        if choice != "unknown":
            log(f"💾 Legacy click detected: Choice {choice} (email-based matching required)")
        
        log(f"ℹ️ Instantly.ai will send webhook → automatic reply will be sent (requires email match)")
        return PlainTextResponse("", status_code=204)

    @app.get("/logs")
    def logs():
        """Get all logs"""
        return list(LOGS)

    @app.get("/logs/get-requests")
    def logs_get_requests():
        """Filter logs to show only email click tracking GET requests and webhook events"""
        email_logs = [
            log_entry for log_entry in LOGS 
            if any(keyword in log_entry.get("m", "") for keyword in [
                "EMAIL_CLICK_REQUEST", "EMAIL_CLICK_RESPONSE", "LINK_CLICKED",
                "EMAIL_MATCHING", "EMAIL_STORED", "Stored choice", "Matched",
                "REPLY_SENT", "REPLY_FAILED", "REPLY_START", "REPLY_API",
                "REPLY_RESPONSE", "REPLY_SUCCESS", "REPLY_ERROR", "REPLY_WARNING",
                "REPLY_VERIFIED", "REPLY_DETAILS", "REPLY_PREPARATION",
                "WEBHOOK", "webhook", "WEBHOOK_ENDPOINT", "WEBHOOK_PAYLOAD",
                "WEBHOOK_EVENT_TYPE", "WEBHOOK_LEAD_EMAIL", "WEBHOOK_EMAIL_ACCOUNT",
                "WEBHOOK_CAMPAIGN_ID", "WEBHOOK_PROCESSING", "link_clicked",
                "EMAIL_ID", "EMAIL_UUID", "UUID", "API_CALL", "API_RESPONSE",
                "API_RESULT", "API_ERROR", "EMAIL_CLICK_STORED", "EMAIL_CLICK_WAITING",
                "FULL_PAYLOAD", "LINK_CLICK_WEBHOOK", "EMAIL_MATCHING_START",
                "EMAIL_MATCHING_SUCCESS", "EMAIL_MATCHING_FAILED",
                "EMAIL_MATCHING_NO_RESULT", "EMAIL_MATCHING_COMPLETE", "DEBUG"
            ])
        ]
        return list(email_logs[-100:])

    @app.get("/logs/live")
    def logs_live_html():
        """Live log viewer page"""
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
                let loadedLogs = new Set();
                
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
                
                async function initialLoad() {
                    try {
                        const response = await fetch('/logs/get-requests');
                        const logs = await response.json();
                        const container = document.getElementById('logs');
                        
                        if (logs.length === 0) {
                            container.innerHTML = '<p style="color: #858585;">No logs yet. Waiting for activity...</p>';
                            return;
                        }
                        
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
                
                initialLoad();
                setInterval(appendNewLogs, 2000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(html)

    @app.post("/logs/clear")
    def clear_logs():
        """Clear all logs"""
        LOGS.clear()
        return {"ok": True, "message": "Logs cleared"}

    @app.get("/status")
    def status():
        """Check webhook configuration status"""
        return {
            "webhook_url": f"{BACKEND_BASE_URL}/webhook/instantly",
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
        """Test page with clickable links"""
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
        """Simulate an Instantly.ai webhook for testing"""
        test_payload = {
            "step": 1,
            "email": "test@example.com",
            "variant": 1,
            "timestamp": datetime.now().isoformat(),
            "workspace": "test-workspace-12345",
            "event_type": "link_clicked",
            "lead_email": "test@example.com",
            "unibox_url": None,
            "campaign_id": None,
            "campaign_name": "Test Campaign",
            "email_account": INSTANTLY_EACCOUNT or "test@example.com"
        }
        
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

    @app.get("/{path_choice}")
    async def link_click(path_choice: str, request: Request):
        """Handle path-based links like /settle, /close, /human - catch-all route at end"""
        skip_paths = {"favicon.ico", "robots.txt", ".well-known"}
        path_lower = path_choice.lower()
        if path_lower in skip_paths or any(path_lower.startswith(skip) for skip in skip_paths):
            return PlainTextResponse("", status_code=204)
        
        client_ip = request.client.host if request.client else "unknown"
        choice = PATH_TO_CHOICE.get(path_lower, "unknown")
        
        if choice != "unknown":
            log(f"🔗 LINK_CLICKED: /{path_choice} → choice: {choice} | IP: {client_ip}")

            query_params = dict(request.query_params)
            email_param = (
                query_params.get("email")
                or query_params.get("lead_email")
                or query_params.get("recipient")
            )
            
            if email_param:
                store_email_click(email_param, choice, client_ip)
                log(f"💾 EMAIL_CLICK_STORED: Choice '{choice}' stored for email '{email_param}' - ready for email-based matching")
                log(f"⏳ EMAIL_CLICK_WAITING: Waiting for Instantly.ai webhook to trigger automatic reply")
            else:
                log(f"⚠️ EMAIL_CLICK_NO_EMAIL: Choice '{choice}' detected but NO email parameter - REPLY WILL NOT BE SENT (email-based matching only)")
                log(f"⚠️ EMAIL_CLICK_REQUIRED: Links must include ?email={{email}} parameter for replies to work")
        
        return PlainTextResponse("", status_code=204)

