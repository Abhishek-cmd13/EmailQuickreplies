"""Instantly.ai API integration - UUID lookup, validation, and reply sending"""
import json
import asyncio
import traceback
from datetime import datetime
from typing import Optional, Tuple

import httpx

from config import (
    INSTANTLY_API_KEY, INSTANTLY_EACCOUNT, INSTANTLY_URL,
    UUID_CACHE_TTL_SECONDS, MAX_QUEUE_SIZE
)
from storage import UUID_CACHE, get_queue, QUEUE_PROCESSOR_RUNNING
from logger import log
from rate_limiter import wait_for_rate_limit


async def validate_uuid_for_email(uuid: str, eaccount: str, lead_email: str) -> Tuple[Optional[str], Optional[str]]:
    """Validate that UUID actually corresponds to the given lead_email and get correct subject"""
    if not uuid:
        return None, None
    
    await wait_for_rate_limit()
    
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            url = f"https://api.instantly.ai/api/v2/emails/{uuid}"
            params = {"eaccount": eaccount}
            
            log(f"🔍 UUID_VALIDATION: Validating UUID {uuid} for {lead_email}")
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            
            if r.status_code == 200:
                email_data = r.json()
                email_lead = email_data.get("lead_email") or email_data.get("lead") or email_data.get("to")
                if email_lead and email_lead.lower().strip() == lead_email.lower().strip():
                    subject = (
                        email_data.get("subject") or 
                        email_data.get("email_subject") or 
                        email_data.get("subject_line") or
                        email_data.get("title") or
                        ""
                    )
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


async def find_email_uuid_for_lead(eaccount: str, lead_email: str, campaign_id: str = None, step: int = None) -> Tuple[Optional[str], Optional[str]]:
    """Try to find email uuid and subject for a lead using Instantly.ai API with caching and exact matching"""
    cache_key = f"{lead_email.lower()}:{eaccount}:{campaign_id or 'none'}:{step or 'none'}"
    cached = UUID_CACHE.get(cache_key)
    if cached:
        cache_age = (datetime.now() - cached.get("timestamp", datetime.now())).total_seconds()
        if cache_age < UUID_CACHE_TTL_SECONDS:
            log(f"✅ UUID_CACHE_HIT: Found cached UUID for {lead_email} (age {cache_age:.1f}s)")
            return cached.get("uuid"), cached.get("subject")
        else:
            del UUID_CACHE[cache_key]
            log(f"🧹 UUID_CACHE_EXPIRED: Removed stale cache for {lead_email}")
    
    await wait_for_rate_limit()
    
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            url = "https://api.instantly.ai/api/v2/emails"
            params = {"eaccount": eaccount, "lead": lead_email}
            if campaign_id:
                params["campaign_id"] = campaign_id
            
            log(f"🔍 API_CALL_START: GET {url}")
            log(f"📋 API_PARAMS: {params}")
            if step:
                log(f"📋 FILTERING: Will filter results by step={step} for exact matching")
            
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
            log(f"📡 API_RESPONSE: Status {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                emails = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                log(f"📧 API_RESULT: Found {len(emails)} email(s) for {lead_email}")
                
                if emails:
                    if step is not None:
                        filtered = [e for e in emails if e.get("step") == step]
                        if filtered:
                            log(f"✅ STEP_FILTER_MATCH: Found {len(filtered)} email(s) matching step={step}")
                            emails = filtered
                    
                    if campaign_id:
                        campaign_emails = [e for e in emails if e.get("campaign_id") == campaign_id]
                        if campaign_emails:
                            log(f"✅ CAMPAIGN_FILTER_MATCH: Found {len(campaign_emails)} email(s) matching campaign_id")
                            emails = campaign_emails
                    
                    emails.sort(key=lambda x: x.get("timestamp_created", x.get("timestamp_email", "")), reverse=True)
                    target_email = emails[0]
                    
                    uuid = target_email.get("id")
                    subject = (
                        target_email.get("subject") or 
                        target_email.get("email_subject") or 
                        target_email.get("subject_line") or
                        target_email.get("title") or
                        ""
                    )
                    
                    log(f"💡 DEBUG: Selected email - step={target_email.get('step')}, campaign_id={target_email.get('campaign_id')}, timestamp={target_email.get('timestamp_created')}")
                    
                    if not subject or not subject.strip():
                        log(f"⚠️ WARNING: Subject is empty in API response - this will cause threading issues")
                        subject = "Loan Update"
                    else:
                        log(f"✅ UUID_FOUND: uuid={uuid}, subject={subject}, step={target_email.get('step')}")
                    
                    UUID_CACHE[cache_key] = {
                        "uuid": uuid,
                        "subject": subject,
                        "timestamp": datetime.now()
                    }
                    log(f"💾 UUID_CACHED: Stored UUID for {lead_email} (cache key: {cache_key[:50]}...)")
                    return uuid, subject
                else:
                    log(f"⚠️ UUID_NOT_FOUND: No emails found for {lead_email}")
            elif r.status_code == 429:
                error_text = r.text[:500] if r.text else "No error message"
                log(f"⚠️ API_RATE_LIMITED: Status 429 - Too Many Requests. Error: {error_text}")
                log(f"💡 RATE_LIMIT_QUEUE: Queuing request for retry")
                queue = get_queue()
                if queue.qsize() >= MAX_QUEUE_SIZE:
                    log(f"⚠️ QUEUE_FULL: Queue is full ({queue.qsize()} items), dropping request for {lead_email}")
                else:
                    await queue.put((eaccount, lead_email, campaign_id, step))
                await asyncio.sleep(5)
                log(f"🔄 API_RETRY: Retrying API call after rate limit delay...")
                await wait_for_rate_limit()
                r = await c.get(url, params=params, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
                log(f"📡 API_RESPONSE (retry): Status {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    emails = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    log(f"📧 API_RESULT (retry): Found {len(emails)} email(s) for {lead_email}")
                    if emails:
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
        log(f"❌ EXCEPTION: {str(e)}")
        log(f"💡 TRACEBACK: {traceback.format_exc()[:500]}")
    return None, None


async def reply(eaccount: str, reply_to_uuid: str, subject: str, html: str, recipient_email: Optional[str] = None) -> bool:
    """Send reply email via Instantly.ai API - returns True if successful, False otherwise"""
    log(f"🚀 REPLY_START: Beginning reply process for recipient={recipient_email}")
    
    if not subject or not subject.strip():
        log(f"⚠️ REPLY_WARNING: Empty subject provided - this may cause threading issues")
        subject = "Loan Update"
    
    if not subject.lower().startswith("re:"):
        reply_subject = f"Re: {subject}"
    else:
        reply_subject = subject
    
    if not reply_to_uuid or not reply_to_uuid.strip():
        log(f"❌ REPLY_FAILED: Invalid reply_to_uuid (empty or None) - reply_to_uuid='{reply_to_uuid}'")
        return False
    
    if not eaccount or not eaccount.strip():
        log(f"❌ REPLY_FAILED: Invalid eaccount (empty or None) - eaccount='{eaccount}'")
        return False
    
    log(f"📋 REPLY_INPUTS: eaccount='{eaccount}', reply_to_uuid='{reply_to_uuid}', subject='{reply_subject}', recipient='{recipient_email}'")
    log(f"📋 REPLY_HTML_LENGTH: {len(html)} characters")
    log(f"📋 REPLY_HTML_PREVIEW: {html[:200]}...")
    
    log(f"⏳ REPLY_RATE_LIMIT: Waiting for rate limit clearance...")
    await wait_for_rate_limit()
    log(f"✅ REPLY_RATE_LIMIT: Rate limit cleared, proceeding with API call")
    
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            reply_json = {
                "eaccount": eaccount,
                "reply_to_uuid": reply_to_uuid,
                "subject": reply_subject,
                "body": {"html": html}
            }
            
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
            
            response_body = r.text
            response_body_length = len(response_body) if response_body else 0
            log(f"📡 REPLY_API_RESPONSE_BODY_LENGTH: {response_body_length} characters")
            
            if r.status_code == 429:
                error_response = response_body[:2000] if response_body else "No error message"
                log(f"⚠️ REPLY_RATE_LIMITED: Status 429 - Too Many Requests")
                log(f"⚠️ REPLY_RATE_LIMITED_RESPONSE: {error_response}")
                log(f"💡 REPLY_RETRY: Will retry after rate limit delay")
                await asyncio.sleep(5)
                await wait_for_rate_limit()
                log(f"🔄 REPLY_RETRY: Retrying API call...")
                request_start_time = datetime.now()
                r = await c.post(INSTANTLY_URL, json=reply_json, headers={"Authorization": f"Bearer {INSTANTLY_API_KEY}"})
                request_duration = (datetime.now() - request_start_time).total_seconds()
                response_body = r.text
                log(f"📡 REPLY_API_RESPONSE (retry): Status {r.status_code}, Duration {request_duration:.2f}s")
                log(f"📡 REPLY_API_RESPONSE_BODY (retry): {response_body[:2000]}")
            
            log(f"📋 REPLY_RESPONSE_FULL_BODY: {response_body}")
            
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
                log(f"⚠️ REPLY_WARNING: Non-JSON response from Instantly.ai API - this may indicate an error")
            
            if response_json:
                error_message = (
                    response_json.get("error") or 
                    response_json.get("message") or 
                    response_json.get("errors") or
                    response_json.get("error_message") or
                    response_json.get("error_detail")
                )
                if error_message:
                    log(f"❌ REPLY_ERROR_IN_RESPONSE: {error_message}")
                    log(f"❌ REPLY_FAILED: API returned success status but contains error message")
                    log(f"📋 REPLY_ERROR_FULL: {json.dumps(response_json, indent=2)}")
                    return False
                
                success = response_json.get("success")
                status = response_json.get("status")
                state = response_json.get("state")
                log(f"📋 REPLY_STATUS_FIELDS: success={success}, status={status}, state={state}")
                
                if success is False:
                    log(f"❌ REPLY_FAILED: API response has success=False")
                    return False
                
                if status and status.lower() in ["error", "failed", "rejected", "bounced"]:
                    log(f"❌ REPLY_FAILED: API response status indicates failure - status='{status}'")
                    return False
                
                if state and state.lower() in ["error", "failed", "rejected"]:
                    log(f"❌ REPLY_FAILED: API response state indicates failure - state='{state}'")
                    return False
                
                if success is True:
                    log(f"✅ REPLY_SUCCESS_FIELD: success=True in response")
                
                if status and status.lower() in ["success", "sent", "queued", "accepted", "delivered"]:
                    log(f"✅ REPLY_STATUS_POSITIVE: status='{status}' indicates success")
                
                if state and state.lower() in ["sent", "queued", "accepted", "delivered"]:
                    log(f"✅ REPLY_STATE_POSITIVE: state='{state}' indicates success")
                
                email_id = (
                    response_json.get("id") or 
                    response_json.get("email_id") or 
                    response_json.get("uuid") or
                    response_json.get("email_uuid") or
                    response_json.get("message_id")
                )
                if email_id:
                    log(f"✅ REPLY_EMAIL_ID: Got email ID from response - {email_id}")
                else:
                    log(f"⚠️ REPLY_WARNING: No email ID in response - this might indicate email wasn't queued")
                    log(f"📋 REPLY_ALL_KEYS: {list(response_json.keys())}")
                
                if not email_id and not success and not status:
                    log(f"⚠️ REPLY_WARNING: Response lacks clear success indicators - may not have been sent")
            
            if r.status_code > 299:
                log(f"❌ REPLY_API_ERROR: HTTP Status {r.status_code}")
                log(f"❌ REPLY_API_ERROR_RESPONSE: {response_body[:2000]}")
                log(f"💡 REPLY_DEBUG: Request payload was: {json.dumps(reply_json, indent=2)}")
                return False
            elif r.status_code == 200 or r.status_code == 201:
                log(f"✅ REPLY_API_HTTP_SUCCESS: Status {r.status_code}")
                
                if response_json:
                    has_error = (
                        response_json.get("error") or 
                        response_json.get("errors") or
                        response_json.get("success") is False or
                        (response_json.get("status") and response_json.get("status").lower() in ["error", "failed"])
                    )
                    
                    if has_error:
                        log(f"❌ REPLY_VERIFICATION_FAILED: Response JSON indicates failure despite HTTP {r.status_code}")
                        log(f"📋 REPLY_FAILURE_DETAILS: {json.dumps(response_json, indent=2)}")
                        return False
                    
                    email_id = (
                        response_json.get("id") or 
                        response_json.get("email_id") or 
                        response_json.get("uuid")
                    )
                    
                    if not email_id:
                        log(f"⚠️ REPLY_WARNING: HTTP {r.status_code} but no email ID in response")
                        log(f"⚠️ REPLY_WARNING: This might mean email was accepted but not queued")
                        log(f"📋 REPLY_RESPONSE_KEYS: {list(response_json.keys())}")
                    
                    log(f"✅ REPLY_VERIFIED_SUCCESS: Email reply accepted by Instantly.ai API")
                    log(f"📧 REPLY_DETAILS: Recipient={recipient_email}, Subject='{reply_subject}', UUID={reply_to_uuid}, ResponseEmailID={email_id}")
                    log(f"📋 REPLY_FULL_RESPONSE: {json.dumps(response_json, indent=2)}")
                    return True
                else:
                    log(f"⚠️ REPLY_WARNING: HTTP {r.status_code} but no JSON response")
                    log(f"⚠️ REPLY_WARNING: Response body: {response_body}")
                    if "error" in response_body.lower() or "failed" in response_body.lower():
                        log(f"❌ REPLY_FAILED: Response body contains error keywords")
                        return False
                    log(f"✅ REPLY_VERIFIED_SUCCESS: HTTP {r.status_code} with non-JSON response (may be OK)")
                    log(f"📧 REPLY_DETAILS: Recipient={recipient_email}, Subject='{reply_subject}', UUID={reply_to_uuid}")
                    return True
            else:
                log(f"⚠️ REPLY_UNUSUAL_STATUS: HTTP Status {r.status_code} (expected 200/201)")
                log(f"⚠️ REPLY_RESPONSE: {response_body[:2000]}")
                return False
                
    except httpx.TimeoutException as e:
        log(f"❌ REPLY_TIMEOUT: Request timed out after 30s - {str(e)}")
        return False
    except httpx.RequestError as e:
        log(f"❌ REPLY_REQUEST_ERROR: Network/request error - {str(e)}")
        return False
    except Exception as e:
        log(f"❌ REPLY_EXCEPTION: {str(e)}")
        log(f"❌ REPLY_EXCEPTION_TYPE: {type(e).__name__}")
        log(f"💡 REPLY_TRACEBACK: {traceback.format_exc()}")
        return False


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
            try:
                eaccount, lead_email, campaign_id, step = await asyncio.wait_for(queue.get(), timeout=60.0)
                log(f"🔄 QUEUE_PROCESSOR: Processing queued request for {lead_email} (queue size: {queue.qsize()})")
                await find_email_uuid_for_lead(eaccount, lead_email, campaign_id, step)
                queue.task_done()
                consecutive_errors = 0
            except asyncio.TimeoutError:
                consecutive_errors = 0
                continue
            except Exception as e:
                consecutive_errors += 1
                log(f"❌ QUEUE_PROCESSOR_ERROR: {str(e)} (consecutive errors: {consecutive_errors})")
                if consecutive_errors >= max_consecutive_errors:
                    log(f"⚠️ QUEUE_PROCESSOR_RESTART: Too many consecutive errors, restarting processor")
                    consecutive_errors = 0
                    await asyncio.sleep(10)
                else:
                    await asyncio.sleep(5)
                queue.task_done()
        except Exception as e:
            consecutive_errors += 1
            log(f"❌ QUEUE_PROCESSOR_FATAL_ERROR: {str(e)}")
            if consecutive_errors >= max_consecutive_errors:
                log(f"⚠️ QUEUE_PROCESSOR_RESTART: Too many fatal errors, restarting processor")
                consecutive_errors = 0
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(5)

