from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import os
import logging
from typing import Optional
from dotenv import load_dotenv
from urllib.parse import quote

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
load_dotenv()

# Environment variables
INSTANTLY_API = os.getenv("INSTANTLY_API_KEY")
SENDER = os.getenv("INSTANTLY_EACCOUNT")  # ex → collections@riverline.ai
BACKEND = os.getenv("BACKEND_URL")  # ex → https://reply.riverline.ai

# Quick reply labels
LABELS = {
    "pay_this_month": "💚 I want to pay this month",
    "pay_next_month": "🟡 I want to pay next month",
    "never_pay": "🔴 I'll never pay this loan",
    "connect_human": "👥 Connect me to a human"
}

ALL = list(LABELS.keys())

app = FastAPI(
    title="Email Quick Reply System",
    description="Quick reply system for Instantly.ai email automation",
    version="1.0.0"
)


async def send_reply(uuid: str, subject: str, html: str) -> bool:
    """Send a reply email via Instantly API - ensures all replies stay in same thread"""
    if not INSTANTLY_API or not SENDER:
        logger.error("Instantly API credentials not configured")
        raise HTTPException(
            status_code=500,
            detail="Instantly API credentials not configured"
        )
    
    # Normalize subject to ensure consistent threading
    # Remove any existing "Re: " prefixes to avoid "Re: Re: Re: " chains
    normalized_subject = subject.strip()
    if normalized_subject.lower().startswith("re: "):
        # Already has Re: prefix, use as is
        reply_subject = normalized_subject
    else:
        # Add Re: prefix
        reply_subject = f"Re: {normalized_subject}"
    
    try:
        logger.info(f"Sending reply for UUID: {uuid}, Subject: {reply_subject}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.instantly.ai/api/v2/emails/reply",
                headers={
                    "Authorization": f"Bearer {INSTANTLY_API}",
                    "Content-Type": "application/json"
                },
                json={
                    "reply_to_uuid": uuid,  # Always reply to original UUID for threading
                    "eaccount": SENDER,
                    "subject": reply_subject,  # Consistent subject for threading
                    "body": {"html": html}
                }
            )
            response.raise_for_status()
            logger.info(f"Successfully sent reply for UUID: {uuid}")
            return True
    except httpx.HTTPStatusError as e:
        error_detail = f"Instantly API error: {e.response.status_code}"
        try:
            error_body = e.response.json()
            error_detail = f"{error_detail} - {error_body}"
        except:
            error_detail = f"{error_detail} - {e.response.text}"
        logger.error(f"HTTP error sending reply: {error_detail}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=error_detail
        )
    except httpx.TimeoutException:
        logger.error(f"Timeout sending reply for UUID: {uuid}")
        raise HTTPException(
            status_code=504,
            detail="Instantly API request timed out"
        )
    except Exception as e:
        logger.error(f"Unexpected error sending reply: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reply: {str(e)}"
        )


def create_button(option: str, uuid: str, subject: str) -> str:
    """Create an HTML button link for a quick reply option"""
    # URL encode the subject to handle special characters properly
    encoded_subject = quote(subject, safe='')
    url = f"{BACKEND}/r?uuid={uuid}&subject={encoded_subject}&chosen={option}"
    label = LABELS.get(option, option)
    return (
        f'<a href="{url}" '
        f'style="display:inline-block;padding:12px 20px;background:#4a3aff;'
        f'color:white;border-radius:6px;margin:8px;text-decoration:none;'
        f'font-family:Arial,sans-serif;font-size:14px;">{label}</a><br>'
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Health check endpoint"""
    backend_display = BACKEND or "YOUR_BACKEND_URL"
    return f"""
    <html>
        <head><title>Email Quick Reply System</title></head>
        <body style="font-family:Arial,sans-serif;padding:40px;max-width:800px;margin:0 auto;">
            <h1>Email Quick Reply System</h1>
            <p>System is running! ✅</p>
            <p>Configure your Instantly campaign to use: <code>{backend_display}/r</code></p>
        </body>
    </html>
    """


@app.get("/r", response_class=HTMLResponse)
async def receive(
    chosen: str = Query(..., description="The selected quick reply option"),
    uuid: str = Query(..., description="The email UUID from Instantly (original email UUID)"),
    subject: str = Query(..., description="The email subject")
):
    """
    Handle quick reply selections from email clicks.
    
    This endpoint processes user selections and sends follow-up emails
    with remaining options until all options are exhausted.
    
    IMPORTANT: All replies use the original UUID to maintain email threading.
    """
    logger.info(f"Received quick reply: chosen={chosen}, uuid={uuid}, subject={subject}")
    
    # Validate inputs
    if chosen not in ALL:
        logger.warning(f"Invalid choice received: {chosen}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid choice: {chosen}. Must be one of {ALL}"
        )
    
    if not uuid:
        raise HTTPException(status_code=400, detail="UUID is required")
    
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    
    # Extract original subject (remove any "Re: " prefixes for consistent threading)
    # This ensures all replies have the same base subject for proper threading
    original_subject = subject.strip()
    while original_subject.lower().startswith("re: "):
        original_subject = original_subject[4:].strip()
    
    # Personalized responses for each button choice
    responses = {
        "pay_this_month": {
            "title": "Great! Let's Process Your Payment",
            "message": "Thank you for choosing to pay this month! We appreciate your prompt action. Our team will send you payment instructions within 24 hours. You'll receive a secure payment link that you can use to complete your transaction easily.",
            "next_steps": "Please keep an eye on your email for payment instructions."
        },
        "pay_next_month": {
            "title": "Payment Scheduled for Next Month",
            "message": "We've noted that you'd like to pay next month. No problem! We'll send you a reminder a few days before the due date to help you stay on track. If you'd like to set up a payment plan, we can assist with that as well.",
            "next_steps": "You'll receive a payment reminder before next month's due date."
        },
        "never_pay": {
            "title": "We Understand Your Concern",
            "message": "We understand that you may be facing financial difficulties. Our team wants to work with you to find a solution that works for both parties. Let's explore options like payment plans, settlement agreements, or other arrangements that might be feasible for your situation.",
            "next_steps": "A member of our team will reach out to discuss your options."
        },
        "connect_human": {
            "title": "Connecting You with Our Team",
            "message": "We want to make sure you get the personal attention you deserve! One of our team members will contact you directly within 24 hours to discuss your account and answer any questions you may have. They'll be able to provide personalized assistance and find the best solution for your situation.",
            "next_steps": "Expect a call or email from our team within 24 hours."
        }
    }
    
    # Get the personalized response for the chosen option
    response = responses.get(chosen, {
        "title": "Thank You",
        "message": "We've received your response.",
        "next_steps": "We'll be in touch soon."
    })
    
    # Remaining options = ALL – selected
    remaining = [x for x in ALL if x != chosen]
    
    # Last step → end the loop
    if len(remaining) == 0:
        html = (
            "<html><body style='font-family:Arial,sans-serif;padding:30px;background-color:#f4f4f4;'>"
            "<div style='background-color:white;padding:30px;border-radius:8px;max-width:600px;margin:0 auto;'>"
            f"<h2 style='color:#4a3aff;'>{response['title']}</h2>"
            f"<p style='font-size:16px;line-height:1.6;'>{response['message']}</p>"
            f"<p style='font-size:14px;color:#666;margin-top:20px;'><strong>Next Steps:</strong> {response['next_steps']}</p>"
            "<p style='margin-top:30px;padding-top:20px;border-top:1px solid #eee;color:#999;font-size:14px;'>"
            "Your selection has been recorded. We'll be in touch soon!</p>"
            "</div></body></html>"
        )
        # Always use original UUID and subject for threading
        await send_reply(uuid, original_subject, html)
        return "Flow complete ✔"
    
    # Build next email dynamically with remaining options
    # Pass original_subject to maintain threading
    buttons_html = "".join(create_button(o, uuid, original_subject) for o in remaining)
    
    html = (
        "<html><body style='font-family:Arial,sans-serif;padding:30px;background-color:#f4f4f4;'>"
        "<div style='background-color:white;padding:30px;border-radius:8px;max-width:600px;margin:0 auto;'>"
        f"<h2 style='color:#4a3aff;'>{response['title']}</h2>"
        f"<p style='font-size:16px;line-height:1.6;'>{response['message']}</p>"
        f"<p style='font-size:14px;color:#666;margin-top:20px;'><strong>Next Steps:</strong> {response['next_steps']}</p>"
        "<hr style='border:none;border-top:1px solid #eee;margin:30px 0;'>"
        "<p style='font-weight:bold;margin-bottom:15px;'>Please also let us know about your preference for:</p>"
        f"<div style='margin-top:20px;'>{buttons_html}</div>"
        "</div></body></html>"
    )
    
    # Always use original UUID and subject for threading
    await send_reply(uuid, original_subject, html)
    return "Next email sent ✔"


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "api_configured": bool(INSTANTLY_API),
        "sender_configured": bool(SENDER),
        "backend_configured": bool(BACKEND)
    }

