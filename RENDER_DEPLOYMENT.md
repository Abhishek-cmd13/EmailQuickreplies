# Render Deployment Guide

Complete step-by-step guide for deploying the Email Quick Reply System on Render.

## Render Start Command

Use this exact command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

## Step-by-Step Deployment

### Step 1: Prepare Your Code

Make sure all your code is committed and pushed to GitHub:

```bash
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up or log in (you can use GitHub to sign in)

### Step 3: Create a New Web Service

1. In Render dashboard, click **"New +"** button (top right)
2. Select **"Web Service"**

### Step 4: Connect Your Repository

1. Click **"Connect account"** if not already connected
2. Select your GitHub account
3. Choose the repository: `Abhishek-cmd13/EmailQuickreplies`
4. Click **"Connect"**

### Step 5: Configure Your Web Service

Fill in these settings:

#### Basic Settings:
- **Name:** `email-quick-reply` (or any name you prefer)
- **Region:** Choose closest to your users (e.g., `Oregon (US West)` or `Singapore`)
- **Branch:** `main`
- **Root Directory:** (leave empty, or `./` if your files are in root)

#### Build & Deploy:
- **Environment:** `Python 3`
- **Build Command:** 
  ```bash
  pip install -r requirements.txt
  ```
- **Start Command:** ⭐ **THIS IS THE IMPORTANT ONE** ⭐
  ```bash
  uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
  ```

#### Instance Type:
- **Free tier:** Choose "Free" (service may sleep after inactivity)
- **Paid tier:** Choose "Starter" ($7/month) for always-on service

### Step 6: Set Environment Variables

Before clicking "Create Web Service", add these environment variables:

Click **"Advanced"** → **"Add Environment Variable"** for each:

1. **INSTANTLY_API_KEY**
   - Key: `INSTANTLY_API_KEY`
   - Value: Your Instantly.ai API key

2. **INSTANTLY_EACCOUNT**
   - Key: `INSTANTLY_EACCOUNT`
   - Value: Your email account (e.g., `collections@riverline.ai`)

3. **BACKEND_URL**
   - Key: `BACKEND_URL`
   - Value: `https://your-service-name.onrender.com`
   - ⚠️ **Note:** Update this after first deployment with your actual Render URL

4. **LOG_LEVEL** (Optional)
   - Key: `LOG_LEVEL`
   - Value: `INFO`

### Step 7: Deploy

1. Click **"Create Web Service"**
2. Render will start building and deploying your application
3. This usually takes 2-5 minutes

### Step 8: Get Your Production URL

After deployment completes:

1. Render provides a URL like: `https://email-quick-reply.onrender.com`
2. Copy this URL

### Step 9: Update BACKEND_URL

1. Go to **Environment** tab in your Render service
2. Find `BACKEND_URL` variable
3. Click edit and update the value to match your actual Render URL:
   ```
   https://email-quick-reply.onrender.com
   ```
4. Save - Render will automatically redeploy

### Step 10: Verify Deployment

Test your health endpoint:

```bash
curl https://your-service-name.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "api_configured": true,
  "sender_configured": true,
  "backend_configured": true
}
```

### Step 11: Update Instantly.ai Email Template

In your Instantly.ai campaign email template, replace `YOUR_BACKEND` with your Render URL:

```html
<a href="https://your-service-name.onrender.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month" 
   style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">
   💚 I want to pay this month
</a>
```

## Render Configuration Summary

### Required Settings:
- **Environment:** Python 3
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2`

### Required Environment Variables:
```env
INSTANTLY_API_KEY=your_api_key
INSTANTLY_EACCOUNT=your_email@domain.com
BACKEND_URL=https://your-service-name.onrender.com
```

## Important Notes

### Free Tier Limitations:
- ⚠️ Service sleeps after 15 minutes of inactivity
- First request after sleep may take 30-60 seconds (cold start)
- Limited to 750 hours/month

### Paid Tier Benefits:
- ✅ Service is always running (no cold starts)
- ✅ Better performance
- ✅ More resources

### Custom Domain (Optional):
1. Go to **Settings** → **Custom Domain**
2. Add your domain
3. Update DNS records as instructed
4. Update `BACKEND_URL` to your custom domain

## Monitoring & Logs

### View Logs:
- Go to your service in Render dashboard
- Click **"Logs"** tab
- View real-time logs

### Monitor Health:
- Set up external monitoring (e.g., UptimeRobot) to ping your `/health` endpoint
- Monitor Render dashboard for deployment status

## Updating Your Deployment

When you push changes to GitHub:

1. Render automatically detects changes
2. Triggers a new build and deployment
3. Shows deployment status in dashboard

Or manually trigger:

1. Go to **Manual Deploy** → **Deploy latest commit**

## Troubleshooting

### Build Fails:
- Check logs in Render dashboard
- Verify `requirements.txt` is correct
- Ensure all dependencies are listed

### Service Won't Start:
- Verify start command is correct
- Check logs for errors
- Verify environment variables are set

### 502 Bad Gateway:
- Service might be sleeping (free tier)
- Wait for first request to wake it up
- Check logs for errors
- Verify PORT environment variable

### API Errors:
- Check `INSTANTLY_API_KEY` is correct
- Verify API key has correct scopes
- Check `INSTANTLY_EACCOUNT` matches your Instantly.ai account

## Cost

- **Free Tier:** $0/month (with limitations)
- **Starter Plan:** $7/month (always-on, recommended for production)

## Next Steps

1. ✅ Deploy to Render
2. ✅ Test health endpoint
3. ✅ Update Instantly.ai email template
4. ✅ Send test email
5. ✅ Monitor logs and performance

---

**Start Command for Reference:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

