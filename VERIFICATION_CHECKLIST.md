# Deployment Verification Checklist

Your service is deployed at: **https://emailquickreplies.onrender.com**

## ✅ Verification Steps

### 1. Health Check (PASSING ✅)
```bash
curl https://emailquickreplies.onrender.com/health
```

Should return:
```json
{
  "status": "healthy",
  "api_configured": true,
  "sender_configured": true,
  "backend_configured": true
}
```

✅ **Status: All checks passing!**

### 2. Main Page
Visit: https://emailquickreplies.onrender.com/

Should show:
- "Email Quick Reply System"
- "System is running! ✅"
- "Configure your Instantly campaign to use: `https://emailquickreplies.onrender.com/r`"

**Note:** If it still shows the old URL, wait a minute for the service to finish redeploying, then refresh the page.

### 3. Test Quick Reply Endpoint
```bash
curl "https://emailquickreplies.onrender.com/r?uuid=test123&subject=Test&chosen=pay_this_month"
```

Expected response: `Next email sent ✔` (if API is configured) or an error message indicating what's missing.

### 4. API Documentation
Visit: https://emailquickreplies.onrender.com/docs

Should show interactive API documentation (Swagger UI).

## 📧 Instantly.ai Configuration

### Email Template URL

Use this in your Instantly.ai email template:

```
https://emailquickreplies.onrender.com/r
```

### Full Template Example

```html
<p>Hi there!</p>
<p>Please select your preferred option:</p>

<a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month" 
   style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">
   💚 I want to pay this month
</a><br>

<a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_next_month" 
   style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">
   🟡 I want to pay next month
</a><br>

<a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=never_pay" 
   style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">
   🔴 I'll never pay this loan
</a><br>

<a href="https://emailquickreplies.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=connect_human" 
   style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">
   👥 Connect me to a human
</a>

<p>Thanks!</p>
```

## ✅ Environment Variables Check

Verify in Render dashboard that these are set:

- [x] `INSTANTLY_API_KEY` - Your Instantly.ai API key
- [x] `INSTANTLY_EACCOUNT` - Your email account (e.g., collections@riverline.ai)
- [x] `BACKEND_URL` - Should be `https://emailquickreplies.onrender.com`

## 🧪 Testing the Full Flow

1. **Update Instantly.ai Email Template**
   - Copy the template above
   - Replace all instances of `YOUR_BACKEND` with `https://emailquickreplies.onrender.com/r`
   - Save in Instantly.ai

2. **Send Test Email**
   - Send a test email through your Instantly.ai campaign
   - Click one of the quick reply buttons

3. **Verify Reply**
   - You should receive a reply email with remaining options
   - Continue clicking buttons to test the full flow
   - Last button should show completion message

## 🎉 You're All Set!

Your Email Quick Reply System is now:
- ✅ Deployed on Render
- ✅ Environment variables configured
- ✅ Health checks passing
- ✅ Ready to handle requests

## 🔄 If URL Still Shows Old Value

If the home page still shows the old URL after updating environment variables:

1. **Wait 2-3 minutes** - Service needs to redeploy
2. **Clear browser cache** - Or use incognito mode
3. **Check Render Logs** - Verify deployment completed
4. **Restart Service** - In Render dashboard, try manual redeploy

The environment variable change triggers an automatic redeploy, which usually takes 1-2 minutes.

---

**Your Production URL:** https://emailquickreplies.onrender.com  
**Quick Reply Endpoint:** https://emailquickreplies.onrender.com/r

