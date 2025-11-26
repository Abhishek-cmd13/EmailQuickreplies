# Email Quick Reply System with Instantly.ai

A FastAPI-based quick reply system that integrates with Instantly.ai to handle email interactions through a multi-step conversational flow.

## Features

- ✅ Multi-step quick reply flow
- ✅ Dynamic email generation based on user selections
- ✅ Integration with Instantly.ai API
- ✅ Clean, responsive email templates
- ✅ Error handling and validation

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

Edit `.env` with your credentials:

```env
INSTANTLY_API_KEY=your_instantly_api_key_here
INSTANTLY_EACCOUNT=collections@riverline.ai
BACKEND_URL=https://reply.riverline.ai
```

### 3. Run the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

For production:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Usage

### Email Template for Instantly.ai

Add this HTML template to your Instantly.ai email campaign. Replace `YOUR_BACKEND` with your actual backend URL:

```html
<p>Hi there!</p>

<p>Please select your preferred option:</p>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;">💚 I want to pay this month</a><br>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_next_month" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;">🟡 I want to pay next month</a><br>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=never_pay" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;">🔴 I'll never pay this loan</a><br>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=connect_human" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;">👥 Connect me to a human</a>

<p>Thanks!</p>
```

### How It Works

1. User receives initial email from Instantly.ai with 4 quick reply buttons
2. User clicks a button → triggers a GET request to `/r` endpoint
3. System sends a follow-up email with remaining options (3 options)
4. User clicks another button → system sends email with 2 remaining options
5. Process continues until all options are exhausted
6. Final message confirms the flow is complete

### Customizing Quick Reply Options

Edit the `LABELS` dictionary in `main.py`:

```python
LABELS = {
    "pay_this_month": "💚 I want to pay this month",
    "pay_next_month": "🟡 I want to pay next month",
    "never_pay": "🔴 I'll never pay this loan",
    "connect_human": "👥 Connect me to a human"
}
```

## API Endpoints

### `GET /`
Health check page showing system status.

### `GET /r`
Main endpoint for handling quick reply selections.

**Query Parameters:**
- `chosen` (required): The selected option (e.g., "pay_this_month")
- `uuid` (required): Email UUID from Instantly.ai
- `subject` (required): Email subject

**Example:**
```
GET /r?uuid=abc123&subject=Payment%20Reminder&chosen=pay_this_month
```

### `GET /health`
Returns health status and configuration check.

## Deployment

### Environment Variables

Make sure to set these environment variables in your deployment platform:

- `INSTANTLY_API_KEY`: Your Instantly.ai API key
- `INSTANTLY_EACCOUNT`: Your Instantly.ai email account
- `BACKEND_URL`: The public URL where this service is deployed

## Testing

Test the endpoint locally:

```bash
curl "http://localhost:8000/r?uuid=test123&subject=Test&chosen=pay_this_month"
```

## Notes

- The system automatically tracks which options have been selected
- Each follow-up email only shows remaining options
- The flow completes when all options are exhausted
- All email replies are sent through Instantly.ai API

## API Documentation

This project uses **Instantly.ai API v2**. For detailed API documentation:
- [Official Instantly.ai API v2 Docs](https://developer.instantly.ai/)
- [API Reference Guide](./INSTANTLY_API_REFERENCE.md) - Summary of relevant API endpoints

## License

MIT

