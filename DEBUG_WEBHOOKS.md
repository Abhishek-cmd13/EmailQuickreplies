# Debugging Webhook Issues

## Problem: Webhooks showing in Slack but not in your app

This means Instantly.ai is configured to send webhooks to **Slack**, not to your Render app.

## Solution

### Step 1: Check Instantly.ai Webhook Configuration

1. Go to **Instantly.ai Dashboard** → **Settings** → **Webhooks**
2. Look for webhook URLs configured
3. You should see:
   - ✅ **Your Render URL**: `https://emailquickreplies.onrender.com/webhook/instantly`
   - ❌ **Slack URL** (if present): Something like `https://hooks.slack.com/...`

### Step 2: Configure Your Render Webhook

If your Render URL is NOT listed:

1. Click **"Add Webhook"** or **"New Webhook"**
2. **Webhook URL**: `https://emailquickreplies.onrender.com/webhook/instantly`
3. **Events to track**:
   - ✅ Enable **CLICK** (required)
   - Optional: SENT, OPEN (for future use)
4. **Save**

### Step 3: Multiple Webhooks

Instantly.ai allows multiple webhooks. If Slack is configured:
- Keep both (Slack + Your App) - webhooks will go to BOTH
- OR remove Slack if you only want your app

### Step 4: Verify

1. Go to: `https://emailquickreplies.onrender.com/webhook-status`
2. Check the diagnostic output
3. Click a button in an email
4. Refresh: `https://emailquickreplies.onrender.com/logs`
5. You should see the webhook appear

## Common Issues

### Issue 1: Webhook URL incorrect
- Wrong: `https://emailquickreplies.onrender.com/webhook` (missing `/instantly`)
- Correct: `https://emailquickreplies.onrender.com/webhook/instantly`

### Issue 2: CLICK events not enabled
- Go to webhook settings
- Make sure "CLICK" checkbox is checked

### Issue 3: Render app is sleeping (free tier)
- Free tier spins down after 15 min inactivity
- First request after sleep will be slow (~30 seconds)
- Upgrade to paid plan for always-on service

### Issue 4: Webhooks going to wrong place
- Check Instantly.ai dashboard has your Render URL
- Remove old/incorrect webhook URLs

## Test Endpoint

Use this to test if your endpoint is reachable:

```bash
curl -X POST https://emailquickreplies.onrender.com/webhook/instantly \
  -H "Content-Type: application/json" \
  -d '{"test": "webhook", "event": "click"}'
```

Then check: `https://emailquickreplies.onrender.com/logs`

