# Click Flow: What Happens When a Link is Clicked

## Overview

When a borrower clicks a button in an email, Instantly.ai sends a webhook to your server. Here's the complete flow of actions taken:

## Step-by-Step Flow

### 1. **Webhook Received** (`POST /webhook/instantly`)
   - Instantly.ai sends a webhook payload with click event details
   - The webhook includes:
     - `event`: "click"
     - `email_id`: UUID of the original email
     - `link`: The clicked URL (e.g., `https://riverline.ai/qr?c=close_loan`)
     - `subject`: Email subject
     - `campaign_id`: Campaign identifier
     - `recipient`: Email address of the borrower

### 2. **Logging & Validation**
   - **Full request logged** (headers, body, URL, client IP)
   - **Campaign ID validation**: Checks if `campaign_id` matches `ALLOWED_CAMPAIGN_ID`
     - If mismatch → Request rejected (but still logged)
   - **Event type detection**: Verifies it's a "click" event
     - If not click → Request ignored

### 3. **Extract Data from Webhook**
   - Extract `email_uuid` from payload (for threading)
   - Extract `clicked_link` from payload (e.g., `https://riverline.ai/qr?c=close_loan`)
   - Extract `subject` from payload

### 4. **Parse Choice from URL**
   - Parse the clicked link URL to extract the choice
   - Looks for query parameter `c` or `choice` in the URL
   - Example: `?c=close_loan` → choice = `"close_loan"`
   - Validates choice is in `ALL_CHOICES` list

### 5. **Calculate Remaining Choices**
   - Takes all available choices: `["close_loan", "settle_loan", "never_pay", "need_more_time"]`
   - Removes the clicked choice
   - Result: `["settle_loan", "never_pay", "need_more_time"]`

### 6. **Build Reply Email HTML**
   - Gets response text for the chosen option from `CHOICE_COPY` dictionary
   - Example for "close_loan":
     ```python
     {
         "title": "We're closing your loan",
         "body": "Thank you for confirming you want to close your loan..."
     }
     ```
   - Creates HTML email with:
     - Thank you message for the chosen option
     - **Buttons for remaining choices** (if any)
     - Professional styling

### 7. **Send Reply via Instantly.ai API**
   - Uses Instantly.ai `/emails/reply` endpoint
   - **Critical for threading**: Sets `reply_to_uuid` to the original email's UUID
   - This ensures the reply appears in the same email thread
   - Email sent with:
     - Subject: "Re: [original subject]"
     - HTML body with chosen response + remaining buttons
     - Same thread as original email

### 8. **Return Success Response**
   ```json
   {
     "status": "ok",
     "handled_event": "click",
     "choice": "close_loan",
     "remaining_choices": ["settle_loan", "never_pay", "need_more_time"],
     "email_uuid": "uuid-from-instantly"
   }
   ```

## Visual Flow Diagram

```
Borrower clicks button in email
         ↓
Instantly.ai tracks click
         ↓
Webhook sent to your server
         ↓
Campaign ID validated ✅
         ↓
Choice extracted from URL (?c=close_loan)
         ↓
Remaining choices calculated
         ↓
Reply email built with:
  - Thank you message for chosen option
  - Buttons for remaining 3 choices
         ↓
Reply sent via Instantly.ai API
  (with reply_to_uuid for threading)
         ↓
Reply appears in same email thread
         ↓
Borrower sees response + remaining options
         ↓
Process repeats if borrower clicks again
```

## Key Functions

### `extract_choice_from_link(link: str)`
- Parses URL query parameters
- Extracts `c` or `choice` parameter
- Returns the choice string (e.g., `"close_loan"`)

### `send_reply_same_thread(email_uuid, subject, html_body)`
- Sends reply via Instantly.ai API
- Uses `reply_to_uuid` to maintain threading
- Formats subject as "Re: [original]"

### `build_email_html(chosen: str, remaining: List[str])`
- Gets personalized response for chosen option
- Builds HTML with remaining choice buttons
- Returns complete HTML email body

### `build_buttons_html(remaining_choices: List[str])`
- Creates HTML buttons for each remaining choice
- Each button links to `FRONTEND_ACTION_BASE?c=[choice]`
- Clicking triggers another webhook → recursive flow

## Example Scenario

1. **Initial Email**: Borrower receives email with 4 buttons
2. **Borrower clicks**: "🔵 Close my loan" button
3. **Webhook received**: `?c=close_loan`
4. **Reply sent**: 
   - "We're closing your loan..." message
   - 3 remaining buttons: "Settle", "Never pay", "Need more time"
5. **Borrower clicks again**: "💠 Settle my loan"
6. **Webhook received**: `?c=settle_loan`
7. **Reply sent**:
   - "We're settling your loan..." message
   - 2 remaining buttons: "Never pay", "Need more time"
8. Process continues until all choices are exhausted

## Important Notes

- **Stateless**: No database/storage - choices calculated on-the-fly
- **Threaded**: All replies appear in same email thread via `reply_to_uuid`
- **Recursive**: Each reply contains buttons that trigger new webhooks
- **Campaign-restricted**: Only processes events from `ALLOWED_CAMPAIGN_ID`
- **Logged**: Every step is logged for debugging in `/logs`

## Configuration

Edit these constants in `main.py`:

- `ALL_CHOICES`: List of all available choices
- `CHOICE_LABELS`: Button labels for each choice
- `CHOICE_COPY`: Personalized messages for each choice
- `ALLOWED_CAMPAIGN_ID`: Campaign ID to accept webhooks from
- `FRONTEND_ACTION_BASE`: Base URL for button links

