# How to Use the Email Quick Reply System

## 🚀 Server Status

The server is now running! You can access it at:
- **Main endpoint**: http://localhost:8000
- **Health check**: http://localhost:8000/health
- **API docs**: http://localhost:8000/docs (FastAPI auto-generated docs)

## 📋 Setup Steps

### 1. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp env.example .env
```

Then edit `.env` and add your credentials:

```env
INSTANTLY_API_KEY=your_instantly_api_key_here
INSTANTLY_EACCOUNT=collections@riverline.ai
BACKEND_URL=https://reply.riverline.ai
```

**Important**: 
- Get your `INSTANTLY_API_KEY` from your Instantly.ai dashboard
- Set `INSTANTLY_EACCOUNT` to the email address you're using in Instantly.ai
- Set `BACKEND_URL` to where this server is publicly accessible (not localhost for production)

### 2. Restart the Server

After updating `.env`, restart the server:

```bash
# Stop the current server (Ctrl+C), then:
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 📧 Setting Up in Instantly.ai

### Step 1: Copy the Email Template

Open `email_template_example.html` and copy the HTML content.

### Step 2: Customize the Template

Replace `YOUR_BACKEND` with your actual backend URL. For example:
- Local testing: `http://localhost:8000` (won't work in actual emails)
- Production: `https://reply.riverline.ai` or your deployed URL

### Step 3: Use Instantly Variables

The template uses Instantly.ai variables:
- `{{email_id}}` - Automatically replaced with the email UUID
- `{{subject}}` - Automatically replaced with the email subject

**Example template for Instantly.ai:**

```html
<p>Hi there!</p>
<p>Please select your preferred option:</p>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_this_month" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">💚 I want to pay this month</a><br>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=pay_next_month" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">🟡 I want to pay next month</a><br>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=never_pay" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">🔴 I'll never pay this loan</a><br>

<a href="https://YOUR_BACKEND/r?uuid={{email_id}}&subject={{subject}}&chosen=connect_human" style="display:inline-block;padding:12px 20px;background:#4a3aff;color:white;border-radius:6px;margin:8px 0;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;width:100%;text-align:center;">👥 Connect me to a human</a>

<p>Thanks!</p>
```

### Step 4: Add to Your Campaign

1. Go to your Instantly.ai campaign
2. Edit your email sequence
3. Paste the HTML template into the email editor
4. Make sure to use HTML mode (not plain text)
5. Replace `YOUR_BACKEND` with your actual backend URL

## 🔄 How It Works

### Flow Diagram

```
1. User receives email with 4 buttons
   ↓
2. User clicks a button (e.g., "pay_this_month")
   ↓
3. GET request to: /r?uuid=abc123&subject=...&chosen=pay_this_month
   ↓
4. System sends reply email with 3 remaining options
   ↓
5. User clicks another button
   ↓
6. System sends reply email with 2 remaining options
   ↓
7. User clicks another button
   ↓
8. System sends reply email with 1 remaining option
   ↓
9. User clicks final button
   ↓
10. System sends completion message
```

### Example Interaction

**Initial Email:**
- 4 options: pay_this_month, pay_next_month, never_pay, connect_human

**After User Clicks "pay_this_month":**
- Reply email sent with 3 options: pay_next_month, never_pay, connect_human

**After User Clicks "pay_next_month":**
- Reply email sent with 2 options: never_pay, connect_human

**After User Clicks "never_pay":**
- Reply email sent with 1 option: connect_human

**After User Clicks "connect_human":**
- Completion message: "Thank you for your response! Your selection has been recorded."

## 🧪 Testing Locally

### Test the Endpoint

```bash
curl "http://localhost:8000/r?uuid=test123&subject=Test%20Email&chosen=pay_this_month"
```

Expected response: `Next email sent ✔`

### Test Health Endpoint

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "api_configured": true/false,
  "sender_configured": true/false,
  "backend_configured": true/false
}
```

### View API Documentation

Open in your browser: http://localhost:8000/docs

This provides an interactive API documentation where you can test endpoints directly.

## 🔧 Customizing Options

To change the quick reply options, edit `main.py`:

```python
LABELS = {
    "pay_this_month": "💚 I want to pay this month",
    "pay_next_month": "🟡 I want to pay next month",
    "never_pay": "🔴 I'll never pay this loan",
    "connect_human": "👥 Connect me to a human",
    # Add more options here
}
```

Then update your email template with the new option keys.

## 🌐 Deploying to Production

### Option 1: Deploy to a VPS

1. Push your code to a server
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variables
4. Run with: `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4`

### Option 2: Deploy to Cloud Platforms

**Heroku:**
```bash
heroku create your-app-name
heroku config:set INSTANTLY_API_KEY=your_key
heroku config:set INSTANTLY_EACCOUNT=your_email
heroku config:set BACKEND_URL=https://your-app-name.herokuapp.com
git push heroku main
```

**Railway, Render, Fly.io:**
- Similar process - set environment variables in their dashboards
- Deploy the code
- Update `BACKEND_URL` to your deployed URL

### Important for Production

- Set `BACKEND_URL` to your public URL (not localhost)
- Use HTTPS for security
- Consider adding authentication if needed
- Monitor logs for errors

## 📝 Troubleshooting

### Server won't start
- Check if port 8000 is already in use
- Verify virtual environment is activated
- Check for syntax errors in `main.py`

### Emails not sending
- Verify `INSTANTLY_API_KEY` is correct
- Check `INSTANTLY_EACCOUNT` matches your Instantly.ai email
- Check Instantly.ai API logs for errors
- Verify the endpoint is publicly accessible

### Buttons not working
- Ensure `BACKEND_URL` is set correctly
- Make sure the URL is publicly accessible (not localhost)
- Check that Instantly.ai variables are being replaced correctly

## 🎯 Next Steps

1. ✅ Set up your `.env` file with real credentials
2. ✅ Deploy the server to a public URL
3. ✅ Add the email template to your Instantly.ai campaign
4. ✅ Test with a real email
5. ✅ Monitor responses and adjust as needed

Happy emailing! 🚀

