# Deploy to Render

## Quick Steps

1. **Go to Render Dashboard**: https://dashboard.render.com
2. **Create New Web Service**
3. **Connect GitHub Repository**: `Abhishek-cmd13/EmailQuickreplies`
4. **Configure Settings**:

   - **Name**: `email-quick-replies` (or your choice)
   - **Region**: Choose closest to you
   - **Branch**: `main`
   - **Root Directory**: (leave empty)
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2`
   - **Auto-Deploy**: Yes (optional)

5. **Environment Variables** (in Render dashboard):
   ```
   INSTANTLY_API_KEY=your_instantly_api_key_here
   INSTANTLY_EACCOUNT=collections@riverline.ai
   FRONTEND_ACTION_BASE=https://riverline.ai/qr
   LOG_LEVEL=INFO
   ```

6. **Click "Create Web Service"**

7. **Wait for deployment** (~2-3 minutes)

8. **Get your URL**: `https://your-app-name.onrender.com`

9. **Configure Instantly.ai Webhook**:
   - Go to Instantly.ai dashboard → Webhooks
   - URL: `https://your-app-name.onrender.com/webhook/instantly`
   - Events: Enable `CLICK` events
   - Save

## Verify Deployment

1. Check health: `https://your-app-name.onrender.com/health`
2. View logs: `https://your-app-name.onrender.com/logs`
3. Test webhook: Send a test email and click a button

## Important Notes

- Render free tier spins down after 15 min of inactivity (first request will be slow)
- Upgrade to paid plan for always-on service
- All webhooks will be logged in `/logs` endpoint

