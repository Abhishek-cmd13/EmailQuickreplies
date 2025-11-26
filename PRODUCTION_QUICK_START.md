# Production Deployment - Quick Start Guide

This is a quick reference guide for deploying to production. For detailed instructions, see [DEPLOYMENT.md](./DEPLOYMENT.md).

## 🚀 Fastest Deployment: Railway

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Ready for production"
git push origin main
```

### Step 2: Deploy on Railway

1. Go to [railway.app](https://railway.app) and sign up/login
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository: `Abhishek-cmd13/EmailQuickreplies`
4. Railway will automatically detect and deploy

### Step 3: Set Environment Variables

In Railway dashboard, go to **Variables** tab and add:

```env
INSTANTLY_API_KEY=your_instantly_api_key_here
INSTANTLY_EACCOUNT=collections@riverline.ai
BACKEND_URL=https://your-app-name.up.railway.app
```

**Important:** Railway will provide you with the domain after first deployment. Update `BACKEND_URL` with that domain.

### Step 4: Get Your Production URL

1. Go to **Settings** → **Networking**
2. Railway provides a domain like: `your-app.up.railway.app`
3. Update `BACKEND_URL` variable with this URL (use HTTPS)

### Step 5: Verify Deployment

```bash
curl https://your-app.up.railway.app/health
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

### Step 6: Update Instantly.ai Template

In your Instantly.ai email template, replace `YOUR_BACKEND` with:

```
https://your-app.up.railway.app
```

## 🔄 Alternative: Render

See [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md) for complete Render deployment guide.

### Quick Summary:

**Start Command:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
```

**Build Command:**
```bash
pip install -r requirements.txt
```

### Steps:

1. Go to [render.com](https://render.com) and sign up
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Use the settings above
5. Add environment variables
6. Deploy!

For detailed instructions, see [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md).

## 🔧 Pre-Deployment Checklist

Before deploying:

- [ ] Code is committed and pushed to GitHub
- [ ] `.env` file is NOT committed (it's in `.gitignore`)
- [ ] You have your Instantly.ai API key
- [ ] You know your Instantly.ai email account
- [ ] You're ready to update email templates

## 📝 Post-Deployment Steps

1. **Test Health Endpoint**
   ```bash
   curl https://your-domain.com/health
   ```

2. **Test Reply Endpoint** (optional, with test UUID)
   ```bash
   curl "https://your-domain.com/r?uuid=test123&subject=Test&chosen=pay_this_month"
   ```

3. **Update Instantly.ai Email Template**
   - Replace `YOUR_BACKEND` with your production URL
   - Make sure URL uses HTTPS

4. **Send Test Email**
   - Send a test email through Instantly.ai
   - Click a quick reply button
   - Verify the reply flow works

## 🆘 Troubleshooting

### Health Check Shows API Not Configured

- Verify environment variables are set correctly
- Check for typos in variable names
- Restart the service after adding variables

### 502 Bad Gateway

- Check if service is running
- Verify PORT is set correctly
- Check logs for errors

### API Errors

- Verify API key is correct
- Check API key has email send permissions
- Verify email account is configured in Instantly.ai

## 🔗 Useful Links

- [Railway Dashboard](https://railway.app/dashboard)
- [Render Dashboard](https://dashboard.render.com)
- [Instantly.ai API Docs](https://developer.instantly.ai/)

## 💰 Cost Estimates

- **Railway**: Free $5 credit/month, then pay as you go (~$5-20/month)
- **Render**: Free tier (sleeps after inactivity), paid ~$7/month
- **Fly.io**: Free tier with limits, then pay as you go

---

**Need help?** See the full [DEPLOYMENT.md](./DEPLOYMENT.md) guide for detailed instructions.

