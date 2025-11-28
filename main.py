import os, logging, json
from datetime import datetime
from typing import Dict, Any, Optional, List
from collections import deque
from urllib.parse import quote_plus
import asyncio

import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
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

# Store recent clicks keyed by email so we can match instantly via webhook (EMAIL-BASED ONLY)
RECENT_EMAIL_CLICKS: Dict[str, Dict[str, Any]] = {}
EMAIL_CLICK_TTL_SECONDS = 3600  # one hour safety window

# Cache UUID lookups to avoid excessive API calls (rate limit: 20/min)
# Key: (email, eaccount, campaign_id) -> {uuid, subject, timestamp}
UUID_CACHE: Dict[str, Dict[str, Any]] = {}
UUID_CACHE_TTL_SECONDS = 3600  # Cache UUIDs for 1 hour

# Request queue for rate limiting (429 errors)
# Queue for UUID lookup requests that need to be processed with rate limiting
# Note: asyncio.Queue() will be initialized in startup event
_api_request_queue: Optional[asyncio.Queue] = None
RATE_LIMIT_REQUESTS_PER_MINUTE = 18  # Use 18 instead of 20 to be safe
RATE_LIMIT_WINDOW_SECONDS = 60
REQUEST_TIMESTAMPS: deque = deque(maxlen=RATE_LIMIT_REQUESTS_PER_MINUTE)
QUEUE_PROCESSOR_RUNNING = False
MAX_QUEUE_SIZE = 1000  # Prevent unbounded queue growth

# Pending webhooks waiting for click events (race condition handling)
# Key: normalized_email -> list of pending webhook payloads
PENDING_WEBHOOKS: Dict[str, List[Dict[str, Any]]] = {}
PENDING_WEBHOOK_TTL_SECONDS = 120  # Wait up to 2 minutes for click to arrive

def get_queue() -> asyncio.Queue:
    """Get or create the API request queue"""
    global _api_request_queue
    if _api_request_queue is None:
        # Create queue (event loop will be available in async context)
        _api_request_queue = asyncio.Queue()
    return _api_request_queue

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
    
    # Check if there are pending webhooks waiting for this email (race condition fix)
    if normalized in PENDING_WEBHOOKS:
        pending_list = PENDING_WEBHOOKS[normalized]
        log(f"🔗 RACE_CONDITION_FIX: Found {len(pending_list)} pending webhook(s) for {normalized}, processing now")
        # Process pending webhooks (they will be handled by the webhook processing logic)
        # Clear the pending list - the webhooks will be reprocessed
        del PENDING_WEBHOOKS[normalized]
    
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
    
    # Also prune stale pending webhooks
    pruned_pending = 0
    for email_key, pending_list in list(PENDING_WEBHOOKS.items()):
        # Remove old pending webhooks
        PENDING_WEBHOOKS[email_key] = [
            wh for wh in pending_list 
            if (now - wh.get("timestamp", now)).total_seconds() < PENDING_WEBHOOK_TTL_SECONDS
        ]
        if not PENDING_WEBHOOKS[email_key]:
            del PENDING_WEBHOOKS[email_key]
            pruned_pending += 1
    if pruned_pending > 0:
        log(f"🧹 PENDING_WEBHOOK_CLEANUP: Pruned {pruned_pending} stale pending webhook entries")

async def wait_for_rate_limit():
    """Wait if we've hit the rate limit, clearing old timestamps"""
    now = datetime.now()
    # Remove timestamps older than the rate limit window
    while REQUEST_TIMESTAMPS and (now - REQUEST_TIMESTAMPS[0]).total_seconds() >= RATE_LIMIT_WINDOW_SECONDS:
        REQUEST_TIMESTAMPS.popleft()
    
    # If we're at the limit, wait until we can make another request
    if len(REQUEST_TIMESTAMPS) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
        oldest_ts = REQUEST_TIMESTAMPS[0]
        wait_seconds = RATE_LIMIT_WINDOW_SECONDS - (now - oldest_ts).total_seconds() + 1
        if wait_seconds > 0:
            log(f"⏳ RATE_LIMIT_WAIT: Waiting {wait_seconds:.1f}s before next API request (at limit)")
            await asyncio.sleep(wait_seconds)
            # Re-check and remove expired timestamps after waiting
            now = datetime.now()
            while REQUEST_TIMESTAMPS and (now - REQUEST_TIMESTAMPS[0]).total_seconds() >= RATE_LIMIT_WINDOW_SECONDS:
                REQUEST_TIMESTAMPS.popleft()
    
    # Record this request timestamp
    REQUEST_TIMESTAMPS.append(datetime.now())

async def validate_uuid_for_email(uuid: str, eaccount: str, lead_email: str) -> tuple:
    """Validate that UUID actually corresponds to the given lead_email and get correct subject"""
    if not uuid:
        return None, None
    
    await wait_for_rate_limit()
    
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # Fetch the specific email by UUID to validate
            url = f"https://api.instantly.ai/api/v2/emails/{uuid}"
            params = {"eaccount": eaccount}
            
            log(f"🔍 UUID_VALIDATION: Validating UUID {uuid} for {lead_email}")
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            
            if r.status_code == 200:
                email_data = r.json()
                # Check if this email actually belongs to the lead_email
                email_lead = email_data.get("lead_email") or email_data.get("lead") or email_data.get("to")
                if email_lead and email_lead.lower().strip() == lead_email.lower().strip():
                    subject = (email_data.get("subject") or 
                              email_data.get("email_subject") or 
                              email_data.get("subject_line") or
                              email_data.get("title") or
                              "")
                    log(f"✅ UUID_VALIDATED: UUID {uuid} is valid for {lead_email}, subject='{subject}'")
                    return uuid, subject if subject.strip() else "Loan Update"
                else:
                    log(f"⚠️ UUID_MISMATCH: UUID {uuid} does not belong to {lead_email} (belongs to {email_lead})")
                    return None, None
            else:
                log(f"⚠️ UUID_VALIDATION_FAILED: Status {r.status_code} for UUID {uuid}")
                return None, None
    except Exception as e:
        log(f"❌ UUID_VALIDATION_EXCEPTION: {str(e)}")
        return None, None

async def find_email_uuid_for_lead(eaccount: str, lead_email: str, campaign_id: str = None, step: int = None):
    """Try to find email uuid and subject for a lead using Instantly.ai API with caching and exact matching"""
    # Check cache first to avoid excessive API calls
    # Build cache key including step for more precise matching
    cache_key = f"{lead_email.lower()}:{eaccount}:{campaign_id or 'none'}:{step or 'none'}"
    cached = UUID_CACHE.get(cache_key)
    if cached:
        cache_age = (datetime.now() - cached.get("timestamp", datetime.now())).total_seconds()
        if cache_age < UUID_CACHE_TTL_SECONDS:
            log(f"✅ UUID_CACHE_HIT: Found cached UUID for {lead_email} (age {cache_age:.1f}s)")
            return cached.get("uuid"), cached.get("subject")
        else:
            # Cache expired, remove it
            del UUID_CACHE[cache_key]
            log(f"🧹 UUID_CACHE_EXPIRED: Removed stale cache for {lead_email}")
    
    # Wait for rate limit if needed
    await wait_for_rate_limit()
    
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
            # Note: step parameter may not be supported by API, but we'll filter manually
            
            log(f"🔍 API_CALL_START: GET {url}")
            log(f"📋 API_PARAMS: {params}")
            if step:
                log(f"📋 FILTERING: Will filter results by step={step} for exact matching")
            
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            
            log(f"📡 API_RESPONSE: Status {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                # API returns items array in response
                emails = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                log(f"📧 API_RESULT: Found {len(emails)} email(s) for {lead_email}")
                
                if emails:
                    # Filter by step if provided (for exact matching)
                    if step is not None:
                        filtered = [e for e in emails if e.get("step") == step]
                        if filtered:
                            log(f"✅ STEP_FILTER_MATCH: Found {len(filtered)} email(s) matching step={step}")
                            emails = filtered
                    
                    # Sort by timestamp_created (most recent first) but prefer emails matching campaign_id
                    if campaign_id:
                        # Prioritize emails from the same campaign
                        campaign_emails = [e for e in emails if e.get("campaign_id") == campaign_id]
                        if campaign_emails:
                            log(f"✅ CAMPAIGN_FILTER_MATCH: Found {len(campaign_emails)} email(s) matching campaign_id")
                            emails = campaign_emails
                    
                    # Now sort by timestamp_created (most recent first)
                    emails.sort(key=lambda x: x.get("timestamp_created", x.get("timestamp_email", "")), reverse=True)
                    target_email = emails[0]
                    
                    # API returns "id" field as the uuid
                    uuid = target_email.get("id")
                    # Try multiple possible subject fields from Instantly.ai API
                    subject = (target_email.get("subject") or 
                              target_email.get("email_subject") or 
                              target_email.get("subject_line") or
                              target_email.get("title") or
                              "")
                    
                    log(f"💡 DEBUG: Selected email - step={target_email.get('step')}, campaign_id={target_email.get('campaign_id')}, timestamp={target_email.get('timestamp_created')}")
                    log(f"💡 DEBUG: Subject fields - subject='{target_email.get('subject')}', email_subject='{target_email.get('email_subject')}', subject_line='{target_email.get('subject_line')}', title='{target_email.get('title')}'")
                    
                    if not subject or not subject.strip():
                        log(f"⚠️ WARNING: Subject is empty in API response - this will cause threading issues")
                        log(f"💡 DEBUG: Full email object (first 500 chars): {json.dumps(target_email, indent=2)[:500]}")
                        subject = "Loan Update"  # Fallback - but this is not ideal
                    else:
                        log(f"✅ UUID_FOUND: uuid={uuid}, subject={subject}, step={target_email.get('step')}")
                    
                    # Cache the UUID to avoid future API calls
                    UUID_CACHE[cache_key] = {
                        "uuid": uuid,
                        "subject": subject,
                        "timestamp": datetime.now()
                    }
                    log(f"💾 UUID_CACHED: Stored UUID for {lead_email} (cache key: {cache_key[:50]}...)")
                    
                    return uuid, subject
                else:
                    log(f"⚠️ UUID_NOT_FOUND: No emails found for {lead_email}")
                    log(f"💡 DEBUG: API returned data type: {type(data)}")
                    log(f"💡 DEBUG: Response keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                    log(f"💡 DEBUG: Response data: {json.dumps(data, indent=2)[:500]}")
            elif r.status_code == 429:
                error_text = r.text[:500] if r.text else "No error message"
                log(f"⚠️ API_RATE_LIMITED: Status 429 - Too Many Requests. Error: {error_text}")
                log(f"💡 RATE_LIMIT_QUEUE: Queuing request for retry")
                # Queue the request instead of immediately retrying
                queue = get_queue()
                # Prevent unbounded queue growth
                if queue.qsize() >= MAX_QUEUE_SIZE:
                    log(f"⚠️ QUEUE_FULL: Queue is full ({queue.qsize()} items), dropping request for {lead_email}")
                else:
                    await queue.put((eaccount, lead_email, campaign_id, step))
                # Wait longer before retrying (queue processor will handle it)
                await asyncio.sleep(5)
                log(f"🔄 API_RETRY: Retrying API call after rate limit delay...")
                # Retry once after delay
                await wait_for_rate_limit()
                r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
                log(f"📡 API_RESPONSE (retry): Status {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    emails = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    log(f"📧 API_RESULT (retry): Found {len(emails)} email(s) for {lead_email}")
                    if emails:
                        # Apply same filtering logic
                        if step is not None:
                            filtered = [e for e in emails if e.get("step") == step]
                            if filtered:
                                emails = filtered
                        if campaign_id:
                            campaign_emails = [e for e in emails if e.get("campaign_id") == campaign_id]
                            if campaign_emails:
                                emails = campaign_emails
                        emails.sort(key=lambda x: x.get("timestamp_created", x.get("timestamp_email", "")), reverse=True)
                        latest = emails[0]
                        uuid = latest.get("id")
                        subject = latest.get("subject", "Loan Update")
                        log(f"✅ UUID_FOUND (retry): uuid={uuid}, subject={subject}")
                        
                        # Cache the UUID from retry as well
                        UUID_CACHE[cache_key] = {
                            "uuid": uuid,
                            "subject": subject,
                            "timestamp": datetime.now()
                        }
                        log(f"💾 UUID_CACHED (retry): Stored UUID for {lead_email}")
                        
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

async def process_api_request_queue():
    """Background task to process queued API requests with rate limiting"""
    global QUEUE_PROCESSOR_RUNNING
    if QUEUE_PROCESSOR_RUNNING:
        return
    QUEUE_PROCESSOR_RUNNING = True
    queue = get_queue()
    log(f"🔄 QUEUE_PROCESSOR: Started background queue processor")
    
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while True:
        try:
            # Wait for a queued request (with timeout to allow checking if queue is empty)
            try:
                eaccount, lead_email, campaign_id, step = await asyncio.wait_for(queue.get(), timeout=60.0)
                log(f"🔄 QUEUE_PROCESSOR: Processing queued request for {lead_email} (queue size: {queue.qsize()})")
                # Re-attempt the lookup (will handle rate limiting automatically)
                await find_email_uuid_for_lead(eaccount, lead_email, campaign_id, step)
                queue.task_done()
                consecutive_errors = 0  # Reset error counter on success
            except asyncio.TimeoutError:
                # No requests in queue, continue waiting
                consecutive_errors = 0  # Timeout is not an error
                continue
            except Exception as e:
                consecutive_errors += 1
                log(f"❌ QUEUE_PROCESSOR_ERROR: {str(e)} (consecutive errors: {consecutive_errors})")
                if consecutive_errors >= max_consecutive_errors:
                    log(f"⚠️ QUEUE_PROCESSOR_RESTART: Too many consecutive errors, restarting processor")
                    consecutive_errors = 0
                    await asyncio.sleep(10)  # Longer wait before restart
                else:
                    await asyncio.sleep(5)  # Wait before retrying
                queue.task_done()  # Mark as done even on error to prevent blocking
        except Exception as e:
            consecutive_errors += 1
            log(f"❌ QUEUE_PROCESSOR_FATAL_ERROR: {str(e)}")
            if consecutive_errors >= max_consecutive_errors:
                log(f"⚠️ QUEUE_PROCESSOR_RESTART: Too many fatal errors, restarting processor")
                consecutive_errors = 0
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(5)

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
    
    # ALWAYS use l.riverlinedebtsupport.in for reply email links (redirects to riverline.credit)
    # This ensures reply emails always have the correct domain, regardless of FRONTEND_ACTION_BASE setting
    base_url = "https://l.riverlinedebtsupport.in"
    
    email_suffix = ""
    if recipient_email:
        email_suffix = f"?email={quote_plus(recipient_email)}"

    next_btn = "".join(
        f'<a href="{base_url}/{choice_to_path(r)}{email_suffix}">{CHOICE_LABELS[r]}</a><br>'
        for r in remaining
    ) if remaining else "<p>We'll follow up soon.</p>"
    return f"""
    <b>{msg['title']}</b><br>{msg['body']}<br><br>
    { f"Choose next: <br>{next_btn}" if remaining else "" }
    """

# ───────── SEND REPLY IN SAME THREAD ─────────
async def reply(eaccount: str, reply_to_uuid: str, subject: str, html: str, recipient_email: Optional[str] = None) -> bool:
    """Send reply email via Instantly.ai API - returns True if successful, False otherwise"""
    log(f"🚀 REPLY_START: Beginning reply process for recipient={recipient_email}")
    
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
    
    # Validate inputs
    if not reply_to_uuid or not reply_to_uuid.strip():
        log(f"❌ REPLY_FAILED: Invalid reply_to_uuid (empty or None) - reply_to_uuid='{reply_to_uuid}'")
        return False
    
    if not eaccount or not eaccount.strip():
        log(f"❌ REPLY_FAILED: Invalid eaccount (empty or None) - eaccount='{eaccount}'")
        return False
    
    # Log all inputs for debugging
    log(f"📋 REPLY_INPUTS: eaccount='{eaccount}', reply_to_uuid='{reply_to_uuid}', subject='{reply_subject}', recipient='{recipient_email}'")
    log(f"📋 REPLY_HTML_LENGTH: {len(html)} characters")
    log(f"📋 REPLY_HTML_PREVIEW: {html[:200]}...")
    
    # Apply rate limiting to reply API calls as well
    log(f"⏳ REPLY_RATE_LIMIT: Waiting for rate limit clearance...")
    await wait_for_rate_limit()
    log(f"✅ REPLY_RATE_LIMIT: Rate limit cleared, proceeding with API call")
    
    try:
        async with httpx.AsyncClient(timeout=30) as c:  # Increased timeout to 30s
            # Build reply payload - Instantly.ai might need recipient email
            reply_json = {
                "eaccount": eaccount,
                "reply_to_uuid": reply_to_uuid,
                "subject": reply_subject,
                "body": {"html": html}
            }
            
            # Add recipient email if provided (some APIs require it for verification)
            if recipient_email:
                reply_json["to"] = recipient_email
                reply_json["lead_email"] = recipient_email
                log(f"📋 REPLY_RECIPIENT_ADDED: Added recipient email to payload: {recipient_email}")
            else:
                log(f"⚠️ REPLY_WARNING: No recipient email provided - relying on reply_to_uuid for routing")
            
            log(f"📤 REPLY_API_REQUEST: POST {INSTANTLY_URL}")
            log(f"📤 REPLY_API_HEADERS: Authorization=Bearer {INSTANTLY_API_KEY[:10]}...")
            log(f"📤 REPLY_PAYLOAD_SUMMARY: uuid={reply_to_uuid}, subject={reply_subject}, eaccount={eaccount}, html_length={len(html)}")
            log(f"📤 REPLY_PAYLOAD_FULL: {json.dumps(reply_json, indent=2)}")
            
            request_start_time = datetime.now()
            r = await c.post(INSTANTLY_URL, json=reply_json, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            request_duration = (datetime.now() - request_start_time).total_seconds()
            
            log(f"📡 REPLY_API_RESPONSE: Status {r.status_code}, Duration {request_duration:.2f}s")
            log(f"📡 REPLY_API_RESPONSE_HEADERS: {dict(r.headers)}")
            
            # Get full response body
            response_body = r.text
            response_body_length = len(response_body) if response_body else 0
            log(f"📡 REPLY_API_RESPONSE_BODY_LENGTH: {response_body_length} characters")
            
            if r.status_code == 429:
                error_response = response_body[:2000] if response_body else "No error message"
                log(f"⚠️ REPLY_RATE_LIMITED: Status 429 - Too Many Requests")
                log(f"⚠️ REPLY_RATE_LIMITED_RESPONSE: {error_response}")
                log(f"💡 REPLY_RETRY: Will retry after rate limit delay")
                # Wait and retry once
                await asyncio.sleep(5)
                await wait_for_rate_limit()
                log(f"🔄 REPLY_RETRY: Retrying API call...")
                request_start_time = datetime.now()
                r = await c.post(INSTANTLY_URL, json=reply_json, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
                request_duration = (datetime.now() - request_start_time).total_seconds()
                response_body = r.text
                log(f"📡 REPLY_API_RESPONSE (retry): Status {r.status_code}, Duration {request_duration:.2f}s")
                log(f"📡 REPLY_API_RESPONSE_BODY (retry): {response_body[:2000]}")
            
            # Log full response body FIRST (for debugging)
            log(f"📋 REPLY_RESPONSE_FULL_BODY: {response_body}")
            
            # Parse response
            response_json = None
            try:
                response_json = r.json() if response_body else None
                if response_json:
                    log(f"📋 REPLY_RESPONSE_JSON: {json.dumps(response_json, indent=2)}")
                else:
                    log(f"⚠️ REPLY_RESPONSE_NO_JSON: Response body exists but not JSON - {response_body[:500]}")
            except Exception as json_error:
                log(f"⚠️ REPLY_RESPONSE_NOT_JSON: Could not parse as JSON - {str(json_error)}")
                log(f"📋 REPLY_RESPONSE_RAW: {response_body}")
                # If response is not JSON, log it fully and treat as potential error
                log(f"⚠️ REPLY_WARNING: Non-JSON response from Instantly.ai API - this may indicate an error")
            
            # Check for errors in response JSON
            if response_json:
                # Check for common error fields (more comprehensive)
                error_message = (response_json.get("error") or 
                               response_json.get("message") or 
                               response_json.get("errors") or
                               response_json.get("error_message") or
                               response_json.get("error_detail"))
                
                if error_message:
                    log(f"❌ REPLY_ERROR_IN_RESPONSE: {error_message}")
                    log(f"❌ REPLY_FAILED: API returned HTTP success but contains error message")
                    log(f"📋 REPLY_ERROR_FULL: {json.dumps(response_json, indent=2)}")
                    return False
                
                # Check for success indicators (more comprehensive)
                success = response_json.get("success")
                status = response_json.get("status")
                state = response_json.get("state")
                
                # Log all status fields
                log(f"📋 REPLY_STATUS_FIELDS: success={success}, status={status}, state={state}")
                
                # Check for explicit failures
                if success is False:
                    log(f"❌ REPLY_FAILED: API response has success=False")
                    return False
                
                if status and status.lower() in ["error", "failed", "rejected", "bounced"]:
                    log(f"❌ REPLY_FAILED: API response status indicates failure - status='{status}'")
                    return False
                
                if state and state.lower() in ["error", "failed", "rejected"]:
                    log(f"❌ REPLY_FAILED: API response state indicates failure - state='{state}'")
                    return False
                
                # Log success indicators
                if success is True:
                    log(f"✅ REPLY_SUCCESS_FIELD: success=True in response")
                
                if status and status.lower() in ["success", "sent", "queued", "accepted", "delivered"]:
                    log(f"✅ REPLY_STATUS_POSITIVE: status='{status}' indicates success")
                
                if state and state.lower() in ["sent", "queued", "accepted", "delivered"]:
                    log(f"✅ REPLY_STATE_POSITIVE: state='{state}' indicates success")
                
                # Log any email ID or tracking info
                email_id = (response_json.get("id") or 
                           response_json.get("email_id") or 
                           response_json.get("uuid") or
                           response_json.get("email_uuid") or
                           response_json.get("message_id"))
                if email_id:
                    log(f"✅ REPLY_EMAIL_ID: Got email ID from response - {email_id}")
                else:
                    log(f"⚠️ REPLY_WARNING: No email ID in response - this might indicate email wasn't queued")
                    log(f"📋 REPLY_ALL_KEYS: {list(response_json.keys())}")
                
                # Check if response indicates email was actually queued/sent
                # Some APIs return 200 but email is still processing
                if not email_id and not success and not status:
                    log(f"⚠️ REPLY_WARNING: Response lacks clear success indicators - may not have been sent")
            
            if r.status_code > 299:
                log(f"❌ REPLY_API_ERROR: HTTP Status {r.status_code}")
                log(f"❌ REPLY_API_ERROR_RESPONSE: {response_body[:2000]}")
                log(f"💡 REPLY_DEBUG: Request payload was: {json.dumps(reply_json, indent=2)}")
                return False
            elif r.status_code == 200 or r.status_code == 201:
                log(f"✅ REPLY_API_HTTP_SUCCESS: Status {r.status_code}")
                
                # Final verification - be very strict
                if response_json:
                    # Check again for errors (double check)
                    has_error = (response_json.get("error") or 
                                response_json.get("errors") or
                                response_json.get("success") is False or
                                (response_json.get("status") and response_json.get("status").lower() in ["error", "failed"]))
                    
                    if has_error:
                        log(f"❌ REPLY_VERIFICATION_FAILED: Response JSON indicates failure despite HTTP {r.status_code}")
                        log(f"📋 REPLY_FAILURE_DETAILS: {json.dumps(response_json, indent=2)}")
                        return False
                    
                    # Check if we got an email ID (indicates email was queued)
                    email_id = (response_json.get("id") or 
                               response_json.get("email_id") or 
                               response_json.get("uuid"))
                    
                    if not email_id:
                        log(f"⚠️ REPLY_WARNING: HTTP {r.status_code} but no email ID in response")
                        log(f"⚠️ REPLY_WARNING: This might mean email was accepted but not queued")
                        log(f"📋 REPLY_RESPONSE_KEYS: {list(response_json.keys())}")
                        # Still return True but log warning - some APIs don't return ID immediately
                    
                    log(f"✅ REPLY_VERIFIED_SUCCESS: Email reply accepted by Instantly.ai API")
                    log(f"📧 REPLY_DETAILS: Recipient={recipient_email}, Subject='{reply_subject}', UUID={reply_to_uuid}, ResponseEmailID={email_id}")
                    log(f"📋 REPLY_FULL_RESPONSE: {json.dumps(response_json, indent=2)}")
                    return True
                else:
                    log(f"⚠️ REPLY_WARNING: HTTP {r.status_code} but no JSON response")
                    log(f"⚠️ REPLY_WARNING: Response body: {response_body}")
                    # Non-JSON response might be an error - be cautious
                    if "error" in response_body.lower() or "failed" in response_body.lower():
                        log(f"❌ REPLY_FAILED: Response body contains error keywords")
                        return False
                    # Some APIs return plain text success - log it
                    log(f"✅ REPLY_VERIFIED_SUCCESS: HTTP {r.status_code} with non-JSON response (may be OK)")
                    log(f"📧 REPLY_DETAILS: Recipient={recipient_email}, Subject='{reply_subject}', UUID={reply_to_uuid}")
                    return True
            else:
                # Unusual status code
                log(f"⚠️ REPLY_UNUSUAL_STATUS: HTTP Status {r.status_code} (expected 200/201)")
                log(f"⚠️ REPLY_RESPONSE: {response_body[:2000]}")
                # Treat as failure for safety
                return False
                
    except httpx.TimeoutException as e:
        log(f"❌ REPLY_TIMEOUT: Request timed out after 30s - {str(e)}")
        return False
    except httpx.RequestError as e:
        log(f"❌ REPLY_REQUEST_ERROR: Network/request error - {str(e)}")
        return False
    except Exception as e:
        import traceback
        log(f"❌ REPLY_EXCEPTION: {str(e)}")
        log(f"❌ REPLY_EXCEPTION_TYPE: {type(e).__name__}")
        log(f"💡 REPLY_TRACEBACK: {traceback.format_exc()}")
        return False

# ========== WEBHOOK ==========
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup"""
    # Initialize the queue
    get_queue()
    # Start the queue processor in the background
    asyncio.create_task(process_api_request_queue())
    log(f"🚀 APP_STARTUP: Queue processor started")

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
    
    # Lightweight logging for webhook (avoid heavy JSON dumps in request cycle)
    if request.url.path == "/webhook/instantly":
        # Just log basic info - full payload logged in background
        log(f"📋 WEBHOOK_RECEIVED: {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Only log responses for email click paths
    if request.method == "GET" and is_email_click_path(request.url.path):
        log(f"📤 EMAIL_CLICK_RESPONSE: GET {request.url.path} -> {response.status_code}")
    elif request.url.path == "/webhook/instantly":
        # Fast response logging
        log(f"⚡ WEBHOOK_RESPONSE: {response.status_code} (processed in background)")
    
    return response

async def process_webhook_logic(payload: Dict[str, Any]):
    """Background task: Process webhook payload - matching, UUID lookup, reply sending"""
    try:
        # Log detailed webhook information (handling Instantly.ai actual payload structure)
        event_type = payload.get("event_type") or payload.get("event") or payload.get("type") or "unknown"
        recipient = payload.get("lead_email") or payload.get("email") or payload.get("recipient") or "unknown"
        campaign_id = payload.get("campaign_id") or "unknown"
        campaign_name = payload.get("campaign_name") or "unknown"
        workspace = payload.get("workspace") or "unknown"
        step = payload.get("step") or "unknown"
        email_account = payload.get("email_account") or "unknown"
        
        log(f"📥 WEBHOOK_EVENT_PROCESSING: {event_type}")
        log(f"   👤 Lead Email: {recipient}")
        log(f"   📧 Email Account: {email_account}")
        log(f"   📋 Campaign: {campaign_name} ({campaign_id})")
        log(f"   🔢 Step: {step} | Workspace: {workspace}")
        
        # Check if this is a click event - send automatic reply
        if "click" in event_type.lower():
            log(f"✅ LINK_CLICK_WEBHOOK_RECEIVED from Instantly.ai")

            matching_click = None
            matching_method = None
            recipient_key = (recipient or "").strip().lower()
            
            log(f"🔍 EMAIL_MATCHING_START: Looking for click for email: {recipient_key}")
            
            # PRIMARY: Email-based matching
            if recipient_key:
                # Debug: Log all stored emails
                log(f"💡 DEBUG: RECENT_EMAIL_CLICKS keys: {list(RECENT_EMAIL_CLICKS.keys())}")
                log(f"💡 DEBUG: Looking for key: '{recipient_key}' (type: {type(recipient_key)})")
                
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
                    log(f"💡 DEBUG: Available emails in storage: {list(RECENT_EMAIL_CLICKS.keys())}")
                    # Check for case/whitespace variations - use the matching one
                    for stored_key in RECENT_EMAIL_CLICKS.keys():
                        if stored_key.lower() == recipient_key.lower() and stored_key != recipient_key:
                            log(f"💡 DEBUG: Found similar email (case mismatch): '{stored_key}' vs '{recipient_key}', using stored key")
                            email_click = RECENT_EMAIL_CLICKS.get(stored_key, None)
                            if email_click:
                                matching_click = email_click.get("choice")
                                matching_method = "EMAIL_BASED_NORMALIZED"
                                log(f"✅ EMAIL_MATCHING_SUCCESS: Matched via normalized email for {recipient_key} → choice: {matching_click}")
                                break
                    
                    # If still no match, this might be a race condition (webhook before click)
                    if not matching_click:
                        log(f"⏳ RACE_CONDITION_DETECTED: Webhook arrived before click stored for {recipient_key}, storing as pending")
                        # Store webhook as pending - will be processed when click arrives
                        if recipient_key not in PENDING_WEBHOOKS:
                            PENDING_WEBHOOKS[recipient_key] = []
                        payload["timestamp"] = datetime.now()
                        PENDING_WEBHOOKS[recipient_key].append(payload)
                        log(f"💾 PENDING_WEBHOOK_STORED: Webhook stored as pending for {recipient_key}, will process when click arrives")
                        # Return early - click handler will process this webhook
                        return

            # EMAIL-BASED MATCHING ONLY (time-based matching removed)
            # This is less deterministic, so we only use it if we have UUID validation
            if not matching_click:
                email_uuid_from_payload = payload.get("email_id") or payload.get("email_uuid") or payload.get("uuid")
                if email_uuid_from_payload:
                    # UUID available but no email match - log but don't use time-based matching
                    log(f"❌ EMAIL_MATCHING_FAILED: No stored click found for email {recipient_key} (UUID available from webhook but no email match)")
            
            if matching_click:
                choice = matching_click
                log(f"📧 EMAIL_MATCHING_COMPLETE: Using choice '{choice}' (matched via {matching_method}) for {recipient_key}")
                
                # Get email_account and campaign_id from webhook payload
                eaccount = payload.get("email_account") or INSTANTLY_EACCOUNT
                campaign_id_val = campaign_id if campaign_id != "unknown" else None
                step_val = payload.get("step")
                if isinstance(step_val, (int, str)):
                    try:
                        step_val = int(step_val)
                    except (ValueError, TypeError):
                        step_val = None
                else:
                    step_val = None
                
                # PRIORITY 1: Check if webhook payload contains email_id/uuid directly (THIS IS THE EXACT EMAIL CLICKED)
                email_uuid = payload.get("email_id") or payload.get("email_uuid") or payload.get("uuid")
                original_subject = payload.get("subject", "Loan Update")
                
                if email_uuid:
                    log(f"✅ EMAIL_UUID_FOUND_IN_PAYLOAD: Found email_uuid in webhook payload: {email_uuid} (this is the EXACT email clicked)")
                    log(f"💡 THREADING_FIX: Using UUID from webhook payload ensures reply goes to correct email thread")
                    # VALIDATE UUID: Verify it actually belongs to this lead_email (deterministic fix)
                    validated_uuid, validated_subject = await validate_uuid_for_email(email_uuid, eaccount, recipient)
                    if validated_uuid:
                        email_uuid = validated_uuid
                        original_subject = validated_subject if validated_subject else original_subject
                        log(f"✅ UUID_VALIDATED: UUID confirmed to belong to {recipient_key}")
                    else:
                        log(f"⚠️ UUID_VALIDATION_FAILED: UUID {email_uuid} validation failed, but proceeding (may cause threading issues)")
                        # Continue with original UUID but log warning
                    
                    # Cache the UUID from webhook payload to avoid future API calls
                    cache_key = f"{recipient_key}:{eaccount}:{campaign_id_val or 'none'}:{step_val or 'none'}"
                    UUID_CACHE[cache_key] = {
                        "uuid": email_uuid,
                        "subject": original_subject,
                        "timestamp": datetime.now()
                    }
                    log(f"💾 UUID_CACHED_FROM_PAYLOAD: Stored UUID from webhook payload with step={step_val}")
                else:
                    log(f"🔍 EMAIL_UUID_LOOKUP_START: email_uuid not in payload, checking cache then API...")
                    log(f"🔍 EMAIL_UUID_LOOKUP_START: recipient={recipient_key}, eaccount={eaccount}, campaign_id={campaign_id_val}, step={step_val}")
                    log(f"💡 DEBUG: Full payload email_account='{payload.get('email_account')}', campaign_id='{campaign_id}', step='{step_val}'")
                    log(f"⚠️ WARNING: Webhook missing email_id - will fetch from API (may not match exact clicked email)")
                    
                    # Get email uuid and subject from Instantly.ai API (with caching and step filtering for exact match)
                    email_uuid, original_subject = await find_email_uuid_for_lead(eaccount, recipient, campaign_id_val, step_val)
                
                log(f"🔍 EMAIL_UUID_LOOKUP_RESULT: uuid={email_uuid}, subject={original_subject}")
                
                if email_uuid:
                    # Get remaining choices
                    remaining = [c for c in ALL if c != choice]
                    html = build_html(choice, remaining, recipient)
                    
                    # Log before calling reply
                    log(f"📧 REPLY_PREPARATION: Preparing reply for choice '{choice}' to {recipient_key}")
                    log(f"📧 REPLY_PREPARATION_DETAILS: eaccount={eaccount}, uuid={email_uuid}, subject={original_subject}")
                    log(f"📧 REPLY_PREPARATION_HTML: {html[:300]}...")
                    
                    # Call reply and check if it actually succeeded
                    reply_success = await reply(eaccount, email_uuid, original_subject, html, recipient)
                    
                    if reply_success:
                        log(f"✅ REPLY_SENT: Automatic reply sent successfully for choice '{choice}' to {recipient_key} (matched via {matching_method})")
                        log(f"✅ REPLY_SENT_DETAILS: Email should arrive at {recipient_key} with subject '{original_subject}'")
                    else:
                        log(f"❌ REPLY_FAILED: Reply API call failed for choice '{choice}' to {recipient_key} (matched via {matching_method})")
                        log(f"❌ REPLY_FAILED_DETAILS: Check logs above for detailed error information")
                        log(f"❌ REPLY_FAILED_DEBUG: eaccount={eaccount}, uuid={email_uuid}, subject={original_subject}")
                else:
                    log(f"❌ REPLY_FAILED: Could not find email uuid for {recipient_key}. Reply not sent.")
                    log(f"💡 DEBUG: Webhook payload email_account='{payload.get('email_account')}', campaign_id='{campaign_id}', recipient='{recipient}'")
                    log(f"💡 DEBUG: Using eaccount='{eaccount}', campaign_id_val='{campaign_id_val}'")
            else:
                log(f"❌ EMAIL_MATCHING_NO_RESULT: No matching click found for webhook from {recipient_key}")
    except Exception as e:
        import traceback
        log(f"❌ WEBHOOK_PROCESSING_EXCEPTION: {str(e)}")
        log(f"💡 TRACEBACK: {traceback.format_exc()[:500]}")

@app.post("/webhook/instantly")
async def instantly_webhook(req: Request, bg: BackgroundTasks):
    """Fast webhook endpoint - returns immediately, processes in background"""
    # Log webhook reception IMMEDIATELY (before background processing)
    client_ip = req.client.host if req.client else "unknown"
    log(f"🔔 WEBHOOK_ENDPOINT_CALLED: POST /webhook/instantly from IP: {client_ip}")
    
    try:
        payload = await req.json()
        # Log full payload immediately (before background task)
        log(f"📥 WEBHOOK_PAYLOAD_RECEIVED: {json.dumps(payload, indent=2)}")
        log(f"📋 WEBHOOK_EVENT_TYPE: {payload.get('event_type', 'unknown')}")
        log(f"👤 WEBHOOK_LEAD_EMAIL: {payload.get('lead_email', 'unknown')}")
    except Exception as e:
        # Fast error handling - don't block
        body = await req.body()
        body_str = body.decode('utf-8', errors='ignore')[:200] if body else "(empty)"
        log(f"❌ WEBHOOK_INVALID_JSON: {str(e)} body={body_str[:100]}")
        return {"ok": True, "error": "invalid_json"}
    
    if not payload:
        log(f"⚠️ WEBHOOK_EMPTY_PAYLOAD")
        return {"ok": True, "error": "empty_payload"}
    
    # Extract minimal info for logging (fast)
    event_type = payload.get("event_type") or payload.get("event") or payload.get("type") or "unknown"
    recipient = payload.get("lead_email") or payload.get("email") or payload.get("recipient") or "unknown"
    
    # Minimal logging in request handler (fast response)
    log(f"⚡ WEBHOOK_RECEIVED: {event_type} for {recipient} - queuing for background processing")
    
    # Queue heavy processing to background task
    bg.add_task(process_webhook_logic, payload)
    
    # Return immediately (< 100ms target)
    return {"ok": True, "queued": True}


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
            # Note: Time-based matching removed - only email-based matching is used
            log(f"💾 Tracking redirect: Choice {choice} detected (email-based matching required)")
        
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
    
    # Note: Time-based matching removed - email parameter required for matching
    if choice != "unknown":
        log(f"💾 Legacy click detected: Choice {choice} (email-based matching required)")
    
    log(f"ℹ️ Instantly.ai will send webhook → automatic reply will be sent (requires email match)")
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
            "REPLY_START",
            "REPLY_API",
            "REPLY_RESPONSE",
            "REPLY_SUCCESS",
            "REPLY_ERROR",
            "REPLY_WARNING",
            "REPLY_VERIFIED",
            "REPLY_DETAILS",
            "REPLY_PREPARATION",
            "WEBHOOK",  # Matches WEBHOOK_HEADERS, WEBHOOK EVENT, WEBHOOK_RESPONSE, etc.
            "webhook",  # Case-insensitive match
            "WEBHOOK_ENDPOINT",  # Webhook endpoint called
            "WEBHOOK_PAYLOAD",  # Webhook payload received
            "WEBHOOK_EVENT_TYPE",  # Event type from webhook
            "WEBHOOK_LEAD_EMAIL",  # Lead email from webhook
            "WEBHOOK_PROCESSING",  # Webhook processing exception
            "link_clicked",  # Event type from Instantly.ai
            "EMAIL_ID",
            "EMAIL_UUID",
            "UUID",
            "API_CALL",
            "API_RESPONSE",
            "API_RESULT",
            "API_ERROR",
            "EMAIL_CLICK_STORED",
            "EMAIL_CLICK_WAITING",
            "FULL_PAYLOAD",  # Webhook payload logging
            "LINK_CLICK_WEBHOOK",  # Webhook received message
            "EMAIL_MATCHING_START",  # Matching process
            "EMAIL_MATCHING_SUCCESS",
            "EMAIL_MATCHING_FAILED",
            "EMAIL_MATCHING_NO_RESULT",
            "EMAIL_MATCHING_COMPLETE",
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
        
        # Store the click - EMAIL-BASED MATCHING ONLY (time-based matching removed)
        if email_param:
            store_email_click(email_param, choice, client_ip)
            log(f"💾 EMAIL_CLICK_STORED: Choice '{choice}' stored for email '{email_param}' - ready for email-based matching")
            log(f"⏳ EMAIL_CLICK_WAITING: Waiting for Instantly.ai webhook to trigger automatic reply")
        else:
            log(f"⚠️ EMAIL_CLICK_NO_EMAIL: Choice '{choice}' detected but NO email parameter - REPLY WILL NOT BE SENT (email-based matching only)")
            log(f"⚠️ EMAIL_CLICK_REQUIRED: Links must include ?email={{email}} parameter for replies to work")
    # Don't log unknown paths - just return silently
    
    return PlainTextResponse("",status_code=204)  # invisible

