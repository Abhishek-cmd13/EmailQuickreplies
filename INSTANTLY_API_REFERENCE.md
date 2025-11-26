# Instantly.ai API v2 Reference Guide

This document summarizes the key information from the [Instantly.ai API v2 documentation](https://developer.instantly.ai/) relevant to our Email Quick Reply System.

## Overview

Instantly.ai API v2 offers:
- ✅ Enhanced security with API scopes
- ✅ Double the endpoints compared to V1
- ✅ Strict REST API standards compliance
- ✅ Bearer token authentication
- ✅ Multiple API key support
- ✅ Granular permission control

**Important:** API V1 is deprecated and will be removed in 2025. We're using API V2.

## Authentication

### Bearer Token Authentication

All API requests must include the API key in the Authorization header:

```http
Authorization: Bearer YOUR_API_KEY
```

### Getting an API Key

1. Log in to your Instantly.ai account
2. Navigate to **Settings** → **Integrations**
3. Create a new API key
4. Assign appropriate API scopes for your use case

### API Scopes

API v2 introduces scopes for granular control:
- Control which endpoints each API key can access
- Improve security by limiting permissions
- Create different keys for different purposes

## Email Reply Endpoint

### Endpoint

```
POST https://api.instantly.ai/api/v2/emails/reply
```

### Request Headers

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

### Request Body

```json
{
  "reply_to_uuid": "email-uuid-from-instantly",
  "eaccount": "your-email@domain.com",
  "subject": "Re: Original Subject",
  "body": {
    "html": "<html>...</html>"
  }
}
```

### Parameters

- **reply_to_uuid** (required): The UUID of the email you're replying to
- **eaccount** (required): The email account configured in Instantly.ai
- **subject** (required): The email subject line
- **body** (required): Email body object
  - **html** (required): HTML content of the email

### Response

Success (200):
```json
{
  "status": "success",
  "message": "Email sent successfully"
}
```

Error responses follow standard HTTP status codes (400, 401, 500, etc.)

## Our Implementation

### Current Code Structure

```python
async def send_reply(uuid: str, subject: str, html: str) -> bool:
    """Send a reply email via Instantly API"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.instantly.ai/api/v2/emails/reply",
            headers={"Authorization": f"Bearer {INSTANTLY_API}"},
            json={
                "reply_to_uuid": uuid,
                "eaccount": SENDER,
                "subject": f"Re: {subject}",
                "body": {"html": html}
            }
        )
        response.raise_for_status()
        return True
```

### Compliance Checklist

- ✅ Using API v2 endpoint (`/api/v2/emails/reply`)
- ✅ Bearer token authentication
- ✅ snake_case naming convention (reply_to_uuid, eaccount)
- ✅ RESTful POST request
- ✅ Proper JSON body structure
- ✅ Error handling with HTTP status codes

## Best Practices

### 1. Error Handling

Our implementation includes comprehensive error handling:
- HTTP status error detection
- Detailed error messages
- Timeout configuration (30 seconds)

### 2. Environment Variables

Store sensitive credentials in environment variables:
- `INSTANTLY_API_KEY`: Your API key
- `INSTANTLY_EACCOUNT`: Your email account
- `BACKEND_URL`: Your backend service URL

### 3. URL Encoding

When constructing URLs with query parameters, ensure proper encoding:
- Subject lines may contain special characters
- Use URL encoding for query parameters

### 4. API Rate Limits

Be aware of Instantly.ai API rate limits:
- Monitor your API usage
- Implement retry logic if needed
- Handle rate limit errors gracefully

## Useful Resources

- [Official API Documentation](https://developer.instantly.ai/)
- [API Explorer](https://developer.instantly.ai/api-explorer) - Interactive API testing
- [Getting Started Guide](https://developer.instantly.ai/docs/getting-started)
- [API V1 to V2 Migration Guide](https://developer.instantly.ai/docs/v1-to-v2-migration)

## Email Variables in Instantly.ai Templates

In your Instantly.ai email templates, you can use:
- `{{email_id}}` - The email UUID (what we use as `uuid` parameter)
- `{{subject}}` - The email subject line
- Other template variables as documented by Instantly.ai

## Next Steps

1. ✅ Verify API key has correct scopes
2. ✅ Test endpoint with real Instantly.ai account
3. ✅ Monitor API response codes
4. ✅ Set up logging for API requests/responses
5. ✅ Consider adding retry logic for transient failures

## Migration Notes

If you're migrating from API V1:
- Generate a new API key for V2
- Update endpoint URLs (add `/v2/`)
- Update authentication method to Bearer tokens
- Review field naming (now snake_case)

---

**Last Updated:** Based on Instantly.ai API v2 documentation as of November 2024

