# Update BACKEND_URL in Render

Your service is deployed at: **https://emailquickreplies.onrender.com**

## Current Issue

The service is showing the old backend URL on the home page. You need to update the `BACKEND_URL` environment variable in Render.

## Quick Fix Steps

### 1. Go to Render Dashboard
- Visit: [dashboard.render.com](https://dashboard.render.com)
- Log in to your account

### 2. Open Your Service
- Click on your service: `emailquickreplies`

### 3. Go to Environment Tab
- Click **"Environment"** in the left sidebar

### 4. Update BACKEND_URL
- Find `BACKEND_URL` in the list
- Click the **pencil/edit icon** (✏️) next to it
- Change the value to:
  ```
  https://emailquickreplies.onrender.com
  ```
- Click **"Save Changes"**

### 5. Wait for Redeploy
- Render will automatically redeploy your service
- Wait 1-2 minutes for deployment to complete

### 6. Verify Update
Visit: https://emailquickreplies.onrender.com/

The page should now show:
```
Configure your Instantly campaign to use: https://emailquickreplies.onrender.com/r
```

## Verify Everything Works

### Test Health Endpoint
```bash
curl https://emailquickreplies.onrender.com/health
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

### Test Reply Endpoint (with test data)
```bash
curl "https://emailquickreplies.onrender.com/r?uuid=test123&subject=Test&chosen=pay_this_month"
```

## Update Instantly.ai Email Template

In your Instantly.ai email template, use this URL for all quick reply buttons:

```
https://emailquickreplies.onrender.com/r
```

### Example Template:
```html
<a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month" 
   style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">
   💚 I want to pay this month
</a>
```

## Summary

**Current Render URL:** https://emailquickreplies.onrender.com  
**Backend URL to set:** https://emailquickreplies.onrender.com  
**Quick Reply Endpoint:** https://emailquickreplies.onrender.com/r

---

After updating, your service will be fully configured! 🚀

