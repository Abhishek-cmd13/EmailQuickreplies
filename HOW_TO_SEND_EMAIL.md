# How to Send Email to Borrower via Instantly.ai

This guide will help you send an email to **abhishekgupta1304@gmail.com** with the quick reply buttons using Instantly.ai.

## Prerequisites

- Instantly.ai account set up
- Email account connected in Instantly.ai
- API key configured in your Render environment variables

## Step-by-Step Instructions

### Step 1: Create a Campaign in Instantly.ai

1. Log in to [Instantly.ai](https://app.instantly.ai)
2. Go to **"Campaigns"** in the left sidebar
3. Click **"Create Campaign"** or **"New Campaign"**

### Step 2: Set Up Campaign Settings

1. **Campaign Name:** "Quick Reply Test" (or any name)
2. **Email Account:** Select your connected email account
3. **Campaign Type:** Choose "Email Sequence" or "Single Email"

### Step 3: Add Lead to Campaign

1. Click **"Add Leads"** or **"Import Leads"**
2. Add the borrower email:
   - **Email:** `abhishekgupta1304@gmail.com`
   - **First Name:** Abhishek (optional)
   - **Last Name:** Gupta (optional)

### Step 4: Create Email Template

1. In your campaign, go to **"Email Templates"** or **"Sequence"**
2. Click **"Create Email"** or **"Add Step"**
3. **Subject Line:** For example: "Action Required: Payment Options"

### Step 5: Use the Email Template

1. **Switch to HTML mode** in the email editor
2. Copy the entire content from `email_template_ready_to_use.html`
3. Paste it into the email editor

**OR** use this simplified version:

```html
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
<div style="background-color: white; padding: 30px; border-radius: 8px; max-width: 600px; margin: 0 auto;">
    
    <h2 style="color: #4a3aff;">Hello Abhishek,</h2>
    
    <p>Thank you for your recent communication. We want to make it easy for you to respond and help you find the best solution.</p>
    
    <p style="font-weight: bold;">Please select your preferred option below:</p>
    
    <div style="margin: 30px 0;">
        <a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month" 
           style="display:block;padding:15px 20px;background:#10b981;color:white;border-radius:6px;margin:12px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:16px;text-align:center;font-weight:bold;">
           💚 I want to pay this month
        </a>
        
        <a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_next_month" 
           style="display:block;padding:15px 20px;background:#f59e0b;color:white;border-radius:6px;margin:12px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:16px;text-align:center;font-weight:bold;">
           🟡 I want to pay next month
        </a>
        
        <a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=never_pay" 
           style="display:block;padding:15px 20px;background:#ef4444;color:white;border-radius:6px;margin:12px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:16px;text-align:center;font-weight:bold;">
           🔴 I'll never pay this loan
        </a>
        
        <a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=connect_human" 
           style="display:block;padding:15px 20px;background:#6366f1;color:white;border-radius:6px;margin:12px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:16px;text-align:center;font-weight:bold;">
           👥 Connect me to a human
        </a>
    </div>
    
    <p style="color: #666; font-size: 14px; margin-top: 30px;">
        Your response will help us assist you better. Thank you for your time!
    </p>
    
    <p style="color: #666; font-size: 14px; margin-top: 20px;">
        Best regards,<br>
        <strong>Your Team</strong>
    </p>
    
</div>
</body>
</html>
```

### Step 6: Important - Use Instantly.ai Variables

Make sure the template uses Instantly.ai variables:
- `{{email_id}}` - This will be automatically replaced with the email UUID
- `{{subject}}` - This will be automatically replaced with the email subject

### Step 7: Send Settings

1. Set **"Send Time"** - Choose when to send (immediately or scheduled)
2. Review all settings
3. Click **"Start Campaign"** or **"Send"**

### Step 8: Monitor

1. Go to **"Campaigns"** → Your campaign
2. Check **"Sent"** tab to see if email was sent
3. Monitor **"Replies"** to see responses

## What Happens Next

### When Borrower Clicks a Button:

1. **Button 1 - "Pay this month":**
   - Receives: "Great! Let's Process Your Payment"
   - Message about payment instructions within 24 hours

2. **Button 2 - "Pay next month":**
   - Receives: "Payment Scheduled for Next Month"
   - Message about payment reminder

3. **Button 3 - "Never pay":**
   - Receives: "We Understand Your Concern"
   - Message about exploring payment options

4. **Button 4 - "Connect to human":**
   - Receives: "Connecting You with Our Team"
   - Message about team contacting within 24 hours

### Multi-Step Flow:

- After first click, borrower receives personalized response
- Also receives remaining 3 buttons to choose from
- Process continues until all buttons are selected
- Final message confirms completion

## Testing

### Test the Flow:

1. Send email to `abhishekgupta1304@gmail.com`
2. Check borrower receives the email
3. Click one of the buttons
4. Verify personalized response is received
5. Continue clicking other buttons
6. Verify multi-step flow works correctly

## Troubleshooting

### Email Not Sending:
- Check Instantly.ai campaign is active
- Verify email account is connected
- Check for any errors in Instantly.ai dashboard

### Buttons Not Working:
- Verify URL uses `https://emailquickreplies.onrender.com/r`
- Check Instantly.ai variables `{{email_id}}` and `{{subject}}` are in template
- Ensure template is in HTML mode (not plain text)

### Replies Not Coming:
- Check Render logs for errors
- Verify API key is correct in Render environment variables
- Check Instantly.ai API status

## Alternative: Send Test Email Directly

If you want to send a test email immediately without a full campaign:

1. Go to **"Email Templates"** in Instantly.ai
2. Create a new template with the HTML above
3. Use **"Send Test Email"** feature
4. Enter `abhishekgupta1304@gmail.com` as recipient
5. Send test email

---

**Ready to send?** Follow the steps above to send your email with personalized quick reply buttons!

