# Instantly.ai Webhook Payload Structure

Based on the [Instantly.ai API V2 documentation](https://developer.instantly.ai/api/v2/webhook/def-37), here's what the webhook payload looks like:

## Base Fields (Always Present)

According to Instantly.ai API documentation, webhook payloads include these base fields:

- **`timestamp`**: ISO 8601 timestamp indicating when the event occurred
- **`event_type`**: Type of event (e.g., `email_link_clicked`, `email_sent`, `email_opened`, `reply_received`, etc.)
- **`workspace`**: UUID of the workspace associated with the event
- **`campaign_id`**: UUID of the campaign related to the event
- **`campaign_name`**: Name of the campaign

## Event Type: `email_link_clicked`

For click events (what we're handling), the payload structure is:

```json
{
  "timestamp": "2025-01-15T10:30:00.000Z",
  "event_type": "email_link_clicked",
  "workspace": "019ac285-166a-791a-87fb-fb690759877b",
  "campaign_id": "e205ce46-f772-42fd-a81c-40eaa996f54e",
  "campaign_name": "Loan Follow-up Campaign",
  "lead_email": "borrower@example.com",
  "email_id": "uuid-of-email-that-was-clicked",
  "email_account": "collections@riverline.ai",
  "link": "https://riverline.ai/qr?c=close_loan",
  "clicked_url": "https://riverline.ai/qr?c=close_loan",
  "subject": "Update about your loan",
  "step": 1,
  "variant": 1,
  "unibox_url": "https://app.instantly.ai/unibox/..."
}
```

## How Our Code Handles It

Our current code tries to extract fields from various possible names:

### Event Type Detection
```python
def detect_event_type(payload):
    return (
        payload.get("event")
        or payload.get("type")
        or payload.get("event_type")  # ← Official field name
        or ""
    )
```

### Campaign ID Extraction
```python
def get_campaign_id(payload):
    return (
        payload.get("campaign_id")  # ← Official field name
        or payload.get("campaign")
        or payload.get("campaignId")
    )
```

### Email UUID Extraction
```python
def get_email_uuid(payload):
    return (
        payload.get("email_id")  # ← Official field name
        or payload.get("email_uuid")
        or payload.get("id")
        or payload.get("emailId")
    )
```

### Clicked Link Extraction
```python
def get_clicked_link(payload):
    return (
        payload.get("link")  # ← Official field name
        or payload.get("url")
        or payload.get("clicked_url")  # ← Also official
        or payload.get("clickedLink")
    )
```

## Complete Example Payload

Based on the official documentation, a full `email_link_clicked` webhook payload would look like:

```json
{
  "timestamp": "2025-01-15T14:23:45.123Z",
  "event_type": "email_link_clicked",
  "workspace": "019ac285-166a-791a-87fb-fb690759877b",
  "campaign_id": "e205ce46-f772-42fd-a81c-40eaa996f54e",
  "campaign_name": "Loan Quick Replies",
  "lead_email": "borrower@example.com",
  "email_id": "019ac285-166a-791a-87fb-fb68878bffb3",
  "email_account": "collections@riverline.ai",
  "link": "https://riverline.ai/qr?c=close_loan",
  "clicked_url": "https://riverline.ai/qr?c=close_loan",
  "subject": "Re: Update about your loan",
  "step": 1,
  "variant": 1,
  "unibox_url": "https://app.instantly.ai/unibox/thread/abc123"
}
```

## Webhook Configuration

When creating a webhook via API, you need:

- **`target_hook_url`**: Your webhook endpoint URL (e.g., `https://emailquickreplies.onrender.com/webhook/instantly`)
- **`event_type`**: `"email_link_clicked"` (for click events)
- **`campaign`** (optional): Campaign UUID to filter events (null = all campaigns)
- **`name`** (optional): User-defined name for the webhook

## Available Event Types

From the API documentation, available event types include:

- `"email_link_clicked"` ← **This is what we need**
- `"email_sent"`
- `"email_opened"`
- `"reply_received"`
- `"email_bounced"`
- `"lead_unsubscribed"`
- `"campaign_completed"`
- `"account_error"`
- `"all_events"` (subscribes to all events)

## What We Need to Update

Our code already handles most field names correctly, but we should ensure we're checking for:

1. ✅ `event_type` (not just `event`)
2. ✅ `campaign_id` (correct field name)
3. ✅ `email_id` (correct field name)
4. ✅ `link` or `clicked_url` (both are valid)

The code is already flexible enough to handle variations, but the official field names are:
- `event_type` (not `event`)
- `campaign_id` (not `campaign`)
- `email_id` (not `email_uuid`)
- `link` or `clicked_url`

## References

- [Instantly.ai Webhook API Documentation](https://developer.instantly.ai/api/v2/webhook/def-37)
- [Webhook Events Documentation](https://developer.instantly.ai/webhook-events)

