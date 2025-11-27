# Riverline – Instantly Webhook Reply Backend

A FastAPI-based webhook backend that handles Instantly.ai click events and sends threaded reply emails.

## Features

- ✅ Webhook-based click tracking via Instantly.ai
- ✅ Automatic email threading using Instantly.ai's `email_id`
- ✅ Multi-step conversational flow (remaining options)
- ✅ Stateless design (no database required)
- ✅ Clean, responsive email templates

## How It Works

1. **Initial Email**: You send an email via Instantly.ai with buttons containing URLs like `https://riverline.ai/qr?c=close_loan`
2. **User Clicks**: Instantly.ai tracks the click and sends a webhook to your backend
3. **Webhook Handler**: The backend extracts the choice from the clicked URL
4. **Reply Sent**: System sends a threaded reply with remaining options
5. **Next Click**: Process repeats until all options are exhausted

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and fill in your values:

```bash
cp env.example .env
```

Edit `.env`:

```env
INSTANTLY_API_KEY=your_instantly_api_key_here
INSTANTLY_EACCOUNT=collections@riverline.ai
FRONTEND_ACTION_BASE=https://riverline.ai/qr
```

### 3. Run the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

For production:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Instantly.ai Configuration

### 1. Configure Webhook in Instantly.ai Dashboard

- **Webhook URL**: `https://your-backend.onrender.com/webhook/instantly`
- **Events**: Enable `CLICK` events (and optionally `SENT`/`OPEN` for future use)

### 2. Create Email Template

In your Instantly.ai campaign template, add buttons with URLs pointing to your `FRONTEND_ACTION_BASE`:

```html
<p>Hi {{first_name}},</p>

<p>Please select your preferred option:</p>

<a href="https://riverline.ai/qr?c=close_loan" style="display:block;padding:10px 14px;background:#4a3aff;color:#fff;border-radius:6px;margin:8px 0;text-decoration:none;text-align:center;">
  🔵 Close my loan
</a>

<a href="https://riverline.ai/qr?c=settle_loan" style="display:block;padding:10px 14px;background:#4a3aff;color:#fff;border-radius:6px;margin:8px 0;text-decoration:none;text-align:center;">
  💠 Settle my loan
</a>

<a href="https://riverline.ai/qr?c=never_pay" style="display:block;padding:10px 14px;background:#4a3aff;color:#fff;border-radius:6px;margin:8px 0;text-decoration:none;text-align:center;">
  ⚠️ I will never pay this loan
</a>

<a href="https://riverline.ai/qr?c=need_more_time" style="display:block;padding:10px 14px;background:#4a3aff;color:#fff;border-radius:6px;margin:8px 0;text-decoration:none;text-align:center;">
  ⏳ I need more time
</a>
```

**Important Notes:**
- The URLs don't need to be actual working pages - Instantly.ai just tracks clicks
- Use query parameter `c` or `choice` (e.g., `?c=close_loan`)
- Instantly.ai will send webhooks when users click these links

## API Endpoints

### `POST /webhook/instantly`
Main webhook endpoint that Instantly.ai calls when events occur.

**Expected Payload (click event):**
```json
{
  "event": "click",
  "email_id": "uuid-from-instantly",
  "recipient": "user@example.com",
  "link": "https://riverline.ai/qr?c=close_loan",
  "subject": "Loan update"
}
```

**Response:**
```json
{
  "status": "ok",
  "handled_event": "click",
  "choice": "close_loan",
  "remaining_choices": ["settle_loan", "never_pay", "need_more_time"],
  "email_uuid": "uuid-from-instantly"
}
```

### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "instantly_configured": true,
  "frontend_action_base": "https://riverline.ai/qr"
}
```

## Customizing Options

Edit the `CHOICE_LABELS` and `CHOICE_COPY` dictionaries in `main.py`:

```python
CHOICE_LABELS: Dict[str, str] = {
    "close_loan": "🔵 Close my loan",
    "settle_loan": "💠 Settle my loan",
    # Add more...
}

CHOICE_COPY: Dict[str, Dict[str, str]] = {
    "close_loan": {
        "title": "You'd like to close your loan",
        "body": "Thanks for letting us know...",
    },
    # Add more...
}
```

## Deployment

### Render.com

1. Create a new Web Service
2. Connect your GitHub repository
3. Set environment variables:
   - `INSTANTLY_API_KEY`
   - `INSTANTLY_EACCOUNT`
   - `FRONTEND_ACTION_BASE`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Other Platforms

The application is compatible with any platform that supports Python/FastAPI:
- Heroku
- Fly.io
- Railway
- AWS (Lambda + API Gateway)
- Google Cloud Run
- Azure App Service

## Flow Diagram

```
1. Initial Email (Instantly.ai)
   └─> Contains 4 buttons: [close_loan, settle_loan, never_pay, need_more_time]

2. User Clicks "close_loan"
   └─> Instantly.ai tracks click → sends webhook → Backend receives

3. Backend Sends Reply
   └─> Email with 3 remaining buttons: [settle_loan, never_pay, need_more_time]

4. User Clicks "settle_loan"
   └─> Reply with 2 remaining: [never_pay, need_more_time]

5. Process continues until all options exhausted
   └─> Final message: "We'll be in touch shortly"
```

## Architecture

- **Stateless**: No database needed - each webhook is independent
- **Threading**: Uses Instantly.ai's `email_id` from webhook payload
- **Simple**: ~300 lines of clean Python code
- **Reliable**: Automatic retries handled by Instantly.ai webhook system

## Troubleshooting

### Webhook not receiving events
- Check Instantly.ai dashboard → Webhooks → Ensure URL is correct and active
- Verify `CLICK` events are enabled
- Check server logs for incoming requests

### Emails not threading
- Ensure `email_id` is being sent in webhook payload
- Check that `reply_to_uuid` is using the `email_id` from webhook
- Verify subject line normalization is working

### Choice not parsed from URL
- Ensure URLs use `?c=choice_name` or `?choice=choice_name`
- Check that `FRONTEND_ACTION_BASE` matches your button URLs
- Verify choice names match `CHOICE_LABELS` keys

## License

MIT
