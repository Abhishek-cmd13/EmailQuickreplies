from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import os
from typing import Optional
from dotenv import load_dotenv

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
    """Send a reply email via Instantly API"""
    if not INSTANTLY_API or not SENDER:
        raise HTTPException(
            status_code=500,
            detail="Instantly API credentials not configured"
        )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.instantly.ai/api/v2/emails/reply",
                headers={"Authorization": f"Bearer {INSTANTLY_API}"},
                json={
                    "reply_to_uuid": uuid,
                    "eaccount": SENDER,
                    "subject": f"Re: {subject}",
                    "body": {"html": html}
                }
            )
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Instantly API error: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reply: {str(e)}"
        )


def create_button(option: str, uuid: str, subject: str) -> str:
    """Create an HTML button link for a quick reply option"""
    url = f"{BACKEND}/r?uuid={uuid}&subject={subject}&chosen={option}"
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
    uuid: str = Query(..., description="The email UUID from Instantly"),
    subject: str = Query(..., description="The email subject")
):
    """
    Handle quick reply selections from email clicks.
    
    This endpoint processes user selections and sends follow-up emails
    with remaining options until all options are exhausted.
    """
    # Validate inputs
    if chosen not in ALL:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid choice: {chosen}. Must be one of {ALL}"
        )
    
    if not uuid:
        raise HTTPException(status_code=400, detail="UUID is required")
    
    if not subject:
        raise HTTPException(status_code=400, detail="Subject is required")
    
    # Remaining options = ALL – selected
    remaining = [x for x in ALL if x != chosen]
    
    # Last step → end the loop
    if len(remaining) == 0:
        html = (
            "<html><body style='font-family:Arial,sans-serif;padding:20px;'>"
            "<h2>Thank you for your response!</h2>"
            "<p>Your selection has been recorded. We'll be in touch soon.</p>"
            "</body></html>"
        )
        await send_reply(uuid, subject, html)
        return "Flow complete ✔"
    
    # Build next email dynamically with remaining options
    buttons_html = "".join(create_button(o, uuid, subject) for o in remaining)
    
    html = (
        "<html><body style='font-family:Arial,sans-serif;padding:20px;'>"
        "<h2>Thanks for your response!</h2>"
        "<p>Please choose one more option:</p>"
        f"<div style='margin-top:20px;'>{buttons_html}</div>"
        "</body></html>"
    )
    
    await send_reply(uuid, subject, html)
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

