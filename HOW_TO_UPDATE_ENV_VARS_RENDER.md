# How to Change Environment Variables in Render

## Method 1: From Service Dashboard (Easiest)

### Step-by-Step:

1. **Log in to Render**
   - Go to [dashboard.render.com](https://dashboard.render.com)
   - Sign in to your account

2. **Find Your Service**
   - Click on your service name (e.g., `email-quick-reply`)
   - This opens your service dashboard

3. **Navigate to Environment Tab**
   - In the left sidebar, click on **"Environment"**
   - Or look for the **"Environment"** tab in the top navigation

4. **View Current Variables**
   - You'll see all your current environment variables listed

5. **Add or Edit Variables**
   
   **To ADD a new variable:**
   - Scroll down to the **"Environment Variables"** section
   - Click **"Add Environment Variable"** button
   - Enter:
     - **Key:** (e.g., `INSTANTLY_API_KEY`)
     - **Value:** (your actual value)
   - Click **"Save Changes"**
   
   **To EDIT an existing variable:**
   - Find the variable in the list
   - Click the **pencil/edit icon** next to it
   - Update the **Value** field
   - Click **"Save Changes"**
   
   **To DELETE a variable:**
   - Find the variable
   - Click the **trash/delete icon** next to it
   - Confirm deletion

6. **Auto-Deploy**
   - After saving, Render will automatically redeploy your service
   - You'll see a new deployment starting in the "Events" tab

## Method 2: From Settings

### Alternative Path:

1. Go to your service dashboard
2. Click **"Settings"** in the left sidebar
3. Scroll down to **"Environment Variables"** section
4. Follow the same steps as Method 1

## Visual Guide

```
Render Dashboard
└── Your Service (email-quick-reply)
    ├── Overview
    ├── Logs
    ├── Metrics
    ├── Events
    ├── Environment  ← CLICK HERE
    │   └── Environment Variables
    │       ├── Add Environment Variable [Button]
    │       ├── INSTANTLY_API_KEY [Edit] [Delete]
    │       ├── INSTANTLY_EACCOUNT [Edit] [Delete]
    │       └── BACKEND_URL [Edit] [Delete]
    └── Settings
```

## Required Environment Variables for This Project

Make sure you have these variables set:

### 1. INSTANTLY_API_KEY
```
Key: INSTANTLY_API_KEY
Value: your_instantly_api_key_here
```

### 2. INSTANTLY_EACCOUNT
```
Key: INSTANTLY_EACCOUNT
Value: collections@riverline.ai
(Replace with your actual email account)
```

### 3. BACKEND_URL
```
Key: BACKEND_URL
Value: https://your-service-name.onrender.com
(Replace with your actual Render URL)
```

### Optional: LOG_LEVEL
```
Key: LOG_LEVEL
Value: INFO
(Optional - for logging configuration)
```

## Important Notes

### ⚠️ Automatic Redeployment
- When you change environment variables, Render **automatically redeploys** your service
- The deployment will appear in the **"Events"** tab
- Wait for deployment to complete before testing

### 🔒 Security
- Environment variable **values are hidden** in the dashboard (shown as `•••••`)
- Click on a variable to reveal/view its value
- Never commit environment variables to your code

### ✅ Verification
After updating variables, verify they're loaded:

1. Go to **"Logs"** tab
2. Restart the service or wait for auto-redeploy
3. Check logs for any configuration errors

Or test via API:
```bash
curl https://your-service-name.onrender.com/health
```

Should show:
```json
{
  "status": "healthy",
  "api_configured": true,
  "sender_configured": true,
  "backend_configured": true
}
```

## Common Scenarios

### Scenario 1: Update BACKEND_URL After First Deploy

After your first deployment, Render gives you a URL like:
- `https://email-quick-reply.onrender.com`

1. Go to **Environment** tab
2. Find `BACKEND_URL`
3. Click edit (pencil icon)
4. Update value to your Render URL
5. Save → Auto-redeploys

### Scenario 2: Change API Key

If you need to update your Instantly.ai API key:

1. Go to **Environment** tab
2. Find `INSTANTLY_API_KEY`
3. Click edit
4. Paste new API key
5. Save → Auto-redeploys

### Scenario 3: Add New Variable

To add a new environment variable:

1. Go to **Environment** tab
2. Scroll to bottom
3. Click **"Add Environment Variable"**
4. Enter Key and Value
5. Save → Auto-redeploys

## Troubleshooting

### Variable Not Showing Up?
- Wait for redeployment to complete
- Check if variable name is spelled correctly
- Verify no extra spaces in variable name
- Check logs for errors

### Service Not Working After Update?
- Check logs in **"Logs"** tab
- Verify all required variables are set
- Check variable values are correct (no typos)
- Ensure BACKEND_URL uses HTTPS

### Can't See Variable Values?
- Variable values are hidden for security
- Click on the variable to view/edit its value
- Use the eye icon to reveal the value

## Quick Reference

**Location:** Service Dashboard → Environment Tab → Environment Variables

**Actions:**
- ➕ Add: Click "Add Environment Variable"
- ✏️ Edit: Click pencil icon
- 🗑️ Delete: Click trash icon
- 💾 Save: Click "Save Changes" button

**Result:** Service automatically redeploys

---

**Pro Tip:** Keep a backup of your environment variable values in a secure password manager, as Render hides them for security!

