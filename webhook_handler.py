"""Webhook processing logic"""
import traceback
from datetime import datetime
from typing import Dict, Any

from config import INSTANTLY_EACCOUNT, ALL
from storage import RECENT_EMAIL_CLICKS, PENDING_WEBHOOKS, UUID_CACHE
from logger import log
from email_service import build_html
from instantly_api import validate_uuid_for_email, find_email_uuid_for_lead, reply


async def process_webhook_logic(payload: Dict[str, Any]):
    """Background task: Process webhook payload - matching, UUID lookup, reply sending"""
    try:
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
        
        if "click" in event_type.lower():
            log(f"✅ LINK_CLICK_WEBHOOK_RECEIVED from Instantly.ai")

            matching_click = None
            matching_method = None
            recipient_key = (recipient or "").strip().lower()
            
            log(f"🔍 EMAIL_MATCHING_START: Looking for click for email: {recipient_key}")
            
            if recipient_key:
                log(f"💡 DEBUG: RECENT_EMAIL_CLICKS keys: {list(RECENT_EMAIL_CLICKS.keys())}")
                log(f"💡 DEBUG: Looking for key: '{recipient_key}' (type: {type(recipient_key)})")
                
                email_click = RECENT_EMAIL_CLICKS.get(recipient_key, None)
                if email_click:
                    matching_click = email_click.get("choice")
                    email_ts = email_click.get("timestamp")
                    age = (datetime.now() - email_ts).total_seconds() if email_ts else 0
                    matching_method = "EMAIL_BASED"
                    log(f"✅ EMAIL_MATCHING_SUCCESS: Matched via email for {recipient_key} → choice: {matching_click} (age {age:.1f}s)")
                else:
                    log(f"⚠️ EMAIL_MATCHING_FAILED: No stored click found for email {recipient_key}")
                    log(f"💡 DEBUG: Available emails in storage: {list(RECENT_EMAIL_CLICKS.keys())}")
                    
                    for stored_key in RECENT_EMAIL_CLICKS.keys():
                        if stored_key.lower() == recipient_key.lower() and stored_key != recipient_key:
                            log(f"💡 DEBUG: Found similar email (case mismatch): '{stored_key}' vs '{recipient_key}', using stored key")
                            email_click = RECENT_EMAIL_CLICKS.get(stored_key, None)
                            if email_click:
                                matching_click = email_click.get("choice")
                                matching_method = "EMAIL_BASED_NORMALIZED"
                                log(f"✅ EMAIL_MATCHING_SUCCESS: Matched via normalized email for {recipient_key} → choice: {matching_click}")
                                break
                    
                    if not matching_click:
                        log(f"⏳ RACE_CONDITION_DETECTED: Webhook arrived before click stored for {recipient_key}, storing as pending")
                        if recipient_key not in PENDING_WEBHOOKS:
                            PENDING_WEBHOOKS[recipient_key] = []
                        payload["timestamp"] = datetime.now()
                        PENDING_WEBHOOKS[recipient_key].append(payload)
                        log(f"💾 PENDING_WEBHOOK_STORED: Webhook stored as pending for {recipient_key}, will process when click arrives")
                        return

            if not matching_click:
                email_uuid_from_payload = payload.get("email_id") or payload.get("email_uuid") or payload.get("uuid")
                if email_uuid_from_payload:
                    log(f"❌ EMAIL_MATCHING_FAILED: No stored click found for email {recipient_key} (UUID available from webhook but no email match)")
            
            if matching_click:
                choice = matching_click
                log(f"📧 EMAIL_MATCHING_COMPLETE: Using choice '{choice}' (matched via {matching_method}) for {recipient_key}")
                
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
                
                email_uuid = payload.get("email_id") or payload.get("email_uuid") or payload.get("uuid")
                original_subject = payload.get("subject", "Loan Update")
                
                if email_uuid:
                    log(f"✅ EMAIL_UUID_FOUND_IN_PAYLOAD: Found email_uuid in webhook payload: {email_uuid} (this is the EXACT email clicked)")
                    log(f"💡 THREADING_FIX: Using UUID from webhook payload ensures reply goes to correct email thread")
                    validated_uuid, validated_subject = await validate_uuid_for_email(email_uuid, eaccount, recipient)
                    if validated_uuid:
                        email_uuid = validated_uuid
                        original_subject = validated_subject if validated_subject else original_subject
                        log(f"✅ UUID_VALIDATED: UUID confirmed to belong to {recipient_key}")
                    else:
                        log(f"⚠️ UUID_VALIDATION_FAILED: UUID {email_uuid} validation failed, but proceeding (may cause threading issues)")
                    
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
                    email_uuid, original_subject = await find_email_uuid_for_lead(eaccount, recipient, campaign_id_val, step_val)
                
                log(f"🔍 EMAIL_UUID_LOOKUP_RESULT: uuid={email_uuid}, subject={original_subject}")
                
                if email_uuid:
                    remaining = [c for c in ALL if c != choice]
                    html = build_html(choice, remaining, recipient)
                    
                    log(f"📧 REPLY_PREPARATION: Preparing reply for choice '{choice}' to {recipient_key}")
                    log(f"📧 REPLY_PREPARATION_DETAILS: eaccount={eaccount}, uuid={email_uuid}, subject={original_subject}")
                    log(f"📧 REPLY_PREPARATION_HTML: {html[:300]}...")
                    
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
        log(f"❌ WEBHOOK_PROCESSING_EXCEPTION: {str(e)}")
        log(f"💡 TRACEBACK: {traceback.format_exc()[:500]}")

