# Production Deployment Guide

This guide covers deploying the Email Quick Reply System to production using various platforms.

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Platform Options](#platform-options)
3. [Environment Variables](#environment-variables)
4. [Deployment Steps](#deployment-steps)
5. [Post-Deployment](#post-deployment)
6. [Monitoring & Maintenance](#monitoring--maintenance)

## Pre-Deployment Checklist

### ✅ Requirements

- [ ] Instantly.ai API key generated
- [ ] Email account configured in Instantly.ai
- [ ] Domain or subdomain ready (for production URL)
- [ ] SSL certificate (HTTPS is required)
- [ ] GitHub repository pushed (recommended)
- [ ] Environment variables documented

### ✅ Code Verification

- [ ] All environment variables are configured
- [ ] `BACKEND_URL` points to your production domain
- [ ] Error handling is in place
- [ ] Logging is configured

## Platform Options

### 1. Railway (Recommended - Easiest)

**Pros:** 
- Easy setup
- Automatic HTTPS
- Git-based deployment
- Free tier available

**Steps:**

1. **Sign up**: Go to [railway.app](https://railway.app)

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Configure Environment Variables**:
   ```env
   INSTANTLY_API_KEY=your_api_key_here
   INSTANTLY_EACCOUNT=collections@riverline.ai
   BACKEND_URL=https://your-app-name.up.railway.app
   ```

4. **Set Start Command**:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2
   ```

5. **Deploy**: Railway will auto-deploy on git push

### 2. Render

**Pros:**
- Free tier available
- Automatic HTTPS
- Easy setup

**Steps:**

1. **Sign up**: Go to [render.com](https://render.com)

2. **Create Web Service**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository

3. **Configure**:
   - **Name**: `email-quick-reply`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2`

4. **Environment Variables**:
   - Add all required env vars in the dashboard

5. **Deploy**: Click "Create Web Service"

### 3. Fly.io

**Pros:**
- Global edge network
- Good performance
- CLI-based

**Steps:**

1. **Install Fly CLI**:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login**:
   ```bash
   fly auth login
   ```

3. **Launch App**:
   ```bash
   fly launch
   ```

4. **Set Secrets**:
   ```bash
   fly secrets set INSTANTLY_API_KEY=your_key
   fly secrets set INSTANTLY_EACCOUNT=your_email
   fly secrets set BACKEND_URL=https://your-app.fly.dev
   ```

### 4. Heroku

**Pros:**
- Well-established platform
- Many integrations

**Steps:**

1. **Install Heroku CLI**:
   ```bash
   brew install heroku/brew/heroku
   ```

2. **Login**:
   ```bash
   heroku login
   ```

3. **Create App**:
   ```bash
   heroku create your-app-name
   ```

4. **Set Environment Variables**:
   ```bash
   heroku config:set INSTANTLY_API_KEY=your_key
   heroku config:set INSTANTLY_EACCOUNT=your_email
   heroku config:set BACKEND_URL=https://your-app-name.herokuapp.com
   ```

5. **Deploy**:
   ```bash
   git push heroku main
   ```

### 5. AWS / Google Cloud / Azure

For enterprise deployments, you can deploy to:
- **AWS**: Use Elastic Beanstalk or EC2 with systemd
- **Google Cloud**: Use Cloud Run or App Engine
- **Azure**: Use App Service

See platform-specific guides below.

## Environment Variables

### Required Variables

```env
# Instantly.ai Configuration
INSTANTLY_API_KEY=your_instantly_api_key_here
INSTANTLY_EACCOUNT=collections@riverline.ai

# Backend URL (MUST be HTTPS in production)
BACKEND_URL=https://your-production-domain.com
```

### Optional Variables

```env
# Server Configuration (if needed)
PORT=8000  # Usually set by platform
WORKERS=2  # Number of worker processes
LOG_LEVEL=INFO
```

## Deployment Steps

### Step 1: Prepare Your Code

1. **Commit all changes**:
   ```bash
   git add .
   git commit -m "Prepare for production deployment"
   git push origin main
   ```

2. **Verify .gitignore**:
   - Ensure `.env` is ignored
   - Ensure `venv/` is ignored

### Step 2: Choose Your Platform

Select one of the platforms above based on your needs.

### Step 3: Set Environment Variables

On your chosen platform, set all required environment variables:
- `INSTANTLY_API_KEY`
- `INSTANTLY_EACCOUNT`
- `BACKEND_URL` (must be HTTPS!)

### Step 4: Deploy

Follow platform-specific deployment steps.

### Step 5: Verify Deployment

1. **Check Health Endpoint**:
   ```bash
   curl https://your-production-domain.com/health
   ```

2. **Test Reply Endpoint** (with test UUID):
   ```bash
   curl "https://your-production-domain.com/r?uuid=test&subject=Test&chosen=pay_this_month"
   ```

3. **Check Logs**:
   - Monitor platform logs for errors

## Post-Deployment

### 1. Update Instantly.ai Email Template

Update your email template in Instantly.ai to use your production URL:

```html
<a href="https://your-production-domain.com/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month">
  💚 I want to pay this month
</a>
```

### 2. Test with Real Email

1. Send a test email through Instantly.ai
2. Click one of the quick reply buttons
3. Verify the reply email is sent
4. Continue the flow to ensure it works end-to-end

### 3. Set Up Monitoring

- Monitor uptime (use services like UptimeRobot)
- Set up error alerts
- Monitor API rate limits

### 4. Custom Domain (Optional)

If you want to use a custom domain:

1. **Add Domain** on your platform
2. **Update DNS Records**:
   - Add CNAME record pointing to platform domain
   - Or add A record with platform IP
3. **Update BACKEND_URL** to your custom domain
4. **Wait for SSL** certificate (usually automatic)

## Monitoring & Maintenance

### Health Checks

Monitor your `/health` endpoint:
- Status: `healthy`
- API configured: `true`
- Sender configured: `true`
- Backend configured: `true`

### Logging

Monitor logs for:
- API errors
- Timeout errors
- Invalid requests
- Rate limit warnings

### Updates

To update your production app:

1. Make changes locally
2. Test thoroughly
3. Commit and push to GitHub
4. Platform will auto-deploy (if configured)
5. Or manually trigger deployment

### Scaling

For high traffic:
- Increase number of workers
- Use platform scaling features
- Consider load balancing
- Monitor performance metrics

## Platform-Specific Guides

### Railway Quick Start

1. Install Railway CLI:
   ```bash
   npm i -g @railway/cli
   railway login
   ```

2. In your project:
   ```bash
   railway init
   railway up
   ```

3. Set variables:
   ```bash
   railway variables set INSTANTLY_API_KEY=your_key
   railway variables set INSTANTLY_EACCOUNT=your_email
   railway variables set BACKEND_URL=https://$(railway domain)
   ```

### Render Quick Start

1. Connect GitHub repo in Render dashboard
2. Create new Web Service
3. Use these settings:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables
5. Deploy

### Fly.io Quick Start

1. Use provided `fly.toml` (create if needed)
2. Run:
   ```bash
   fly launch
   fly secrets set INSTANTLY_API_KEY=your_key
   fly secrets set INSTANTLY_EACCOUNT=your_email
   fly secrets set BACKEND_URL=https://your-app.fly.dev
   fly deploy
   ```

## Troubleshooting

### Common Issues

1. **502 Bad Gateway**:
   - Check server is running
   - Verify PORT environment variable
   - Check logs for errors

2. **API Errors**:
   - Verify API key is correct
   - Check API key has correct scopes
   - Verify email account is configured in Instantly.ai

3. **SSL/HTTPS Issues**:
   - Ensure BACKEND_URL uses HTTPS
   - Wait for SSL certificate provisioning
   - Check platform SSL status

4. **Timeout Errors**:
   - Increase timeout in platform settings
   - Check Instantly.ai API status
   - Monitor network connectivity

## Security Best Practices

1. ✅ **Never commit** `.env` file
2. ✅ Use HTTPS only in production
3. ✅ Keep API keys secure
4. ✅ Use environment variables, not hardcoded secrets
5. ✅ Enable platform security features
6. ✅ Monitor for suspicious activity
7. ✅ Keep dependencies updated

## Cost Estimates

### Free Tier Options

- **Railway**: $5 credit/month
- **Render**: Free tier available (sleeps after inactivity)
- **Fly.io**: Free tier with limitations
- **Heroku**: No free tier (starts at $7/month)

### Paid Options

- **Railway**: ~$5-20/month for basic apps
- **Render**: ~$7-25/month
- **Fly.io**: Pay as you go
- **AWS/GCP/Azure**: Pay as you go (can be very cheap)

## Next Steps

1. Choose a deployment platform
2. Set up your production environment
3. Configure environment variables
4. Deploy your application
5. Test thoroughly
6. Update Instantly.ai templates
7. Monitor and maintain

---

**Need Help?** Check platform-specific documentation or open an issue on GitHub.

