"""Email service - building HTML and storing clicks"""
from typing import Optional
from datetime import datetime
from urllib.parse import quote_plus

from config import CHOICE_COPY, CHOICE_LABELS, ALL, EMAIL_CLICK_TTL_SECONDS, PENDING_WEBHOOK_TTL_SECONDS
from storage import RECENT_EMAIL_CLICKS, PENDING_WEBHOOKS
from logger import log


def build_html(choice, remaining, recipient_email: Optional[str] = None):
    """Build HTML email content with remaining choice buttons"""
    msg = CHOICE_COPY.get(choice, {"title": "Noted", "body": "Response received"})
    
    # Map choice to URL path
    def choice_to_path(c):
        mapping = {
            "settle_loan": "settle",
            "close_loan": "close",
            "never_pay": "never",
            "need_more_time": "time"
        }
        return mapping.get(c, "unknown")
    
    # ALWAYS use l.riverlinedebtsupport.in for reply email links
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
        PENDING_WEBHOOKS[email_key] = [
            wh for wh in pending_list 
            if (now - wh.get("timestamp", now)).total_seconds() < PENDING_WEBHOOK_TTL_SECONDS
        ]
        if not PENDING_WEBHOOKS[email_key]:
            del PENDING_WEBHOOKS[email_key]
            pruned_pending += 1
    if pruned_pending > 0:
        log(f"🧹 PENDING_WEBHOOK_CLEANUP: Pruned {pruned_pending} stale pending webhook entries")

