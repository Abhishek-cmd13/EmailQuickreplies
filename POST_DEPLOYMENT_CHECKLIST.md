# Post-Deployment Checklist

Use this checklist to verify your deployment is working correctly.

## ✅ Deployment Verification

### 1. Health Check
Test your health endpoint:

```bash
curl https://your-service-name.onrender.com/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "api_configured": true,
  "sender_configured": true,
  "backend_configured": true
}
```

✅ All should be `true` - if any are `false`, check your environment variables in Render.

### 2. Main Endpoint
Visit in browser or test:

```bash
curl https://your-service-name.onrender.com/
```

Should show: "Email Quick Reply System - System is running! ✅"

### 3. API Documentation
Visit: `https://your-service-name.onrender.com/docs`

Should show interactive API documentation (Swagger UI).

## ✅ Instantly.ai Configuration

### 1. Email Template Updated
- [ ] Replaced `YOUR_BACKEND` with your Render URL
- [ ] Template uses HTTPS URL
- [ ] All 4 quick reply buttons are included
- [ ] Template uses Instantly.ai variables: `{{email_id}}` and `{{subject}}`

### 2. Test Email
- [ ] Send a test email through Instantly.ai
- [ ] Click a quick reply button
- [ ] Verify reply email is received
- [ ] Continue clicking buttons to test the full flow

## ✅ Environment Variables Check

In Render, verify these are set:

- [ ] `INSTANTLY_API_KEY` - Your API key
- [ ] `INSTANTLY_EACCOUNT` - Your email account
- [ ] `BACKEND_URL` - Your Render URL (https://your-service.onrender.com)

## ✅ Monitoring

### 1. Check Logs
- [ ] Logs are visible in Render dashboard
- [ ] No error messages in logs
- [ ] Requests are being logged

### 2. Monitor Performance
- [ ] Service is responding quickly
- [ ] No timeout errors
- [ ] Health checks are passing

## 🎉 Success Indicators

You're all set if:

✅ Health endpoint returns all `true` values  
✅ Test email flow works end-to-end  
✅ Reply emails are being sent  
✅ Logs show successful requests  
✅ No errors in Render dashboard  

## 🔄 Next Steps

1. **Monitor for 24 hours**
   - Watch logs for any issues
   - Test with real emails
   - Verify response times

2. **Scale if needed**
   - If traffic increases, consider upgrading Render plan
   - Monitor API rate limits from Instantly.ai

3. **Custom Domain (Optional)**
   - Set up custom domain in Render
   - Update DNS records
   - Update `BACKEND_URL` to custom domain

4. **Set up Monitoring (Optional)**
   - Use UptimeRobot or similar to monitor health endpoint
   - Set up alerts for downtime

## 🆘 Troubleshooting

### If Health Check Shows `api_configured: false`
- Check `INSTANTLY_API_KEY` is set correctly
- Verify no extra spaces in variable name or value

### If Health Check Shows `sender_configured: false`
- Check `INSTANTLY_EACCOUNT` is set correctly
- Verify email format is correct

### If Health Check Shows `backend_configured: false`
- Check `BACKEND_URL` is set
- Verify URL uses HTTPS (not HTTP)

### If Test Email Doesn't Work
- Check Instantly.ai email template has correct URL
- Verify email account is configured in Instantly.ai
- Check Render logs for errors
- Verify API key has correct scopes

## 📞 Support Resources

- **Render Support**: Check Render documentation or support
- **Instantly.ai API Docs**: https://developer.instantly.ai/
- **Project Documentation**: See README.md and deployment guides

---

**Congratulations on deploying your Email Quick Reply System! 🚀**

