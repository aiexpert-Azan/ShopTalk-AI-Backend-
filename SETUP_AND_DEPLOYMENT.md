# Phone-Based Authentication Implementation Guide

## Overview

ShopTalk AI backend has been updated with a complete phone-based authentication system using **Twilio Verify Service**. This implementation replaces the previous email-based password reset system with a more robust, SMS-based OTP verification system suitable for Pakistani users.

## What Changed

### Removed Components
- ❌ Email-based forgot password (SendGrid email links)
- ❌ In-memory OTP storage with custom expiry logic
- ❌ Email reset code endpoints
- ❌ Custom 6-digit code generation and validation

### New Components
- ✅ Twilio Verify Service for managed OTP delivery
- ✅ SMS-based password reset
- ✅ SMS-based signup OTP verification
- ✅ Phone number as primary auth identifier
- ✅ Pakistani phone format validation (03XXXXXXXXX)
- ✅ International phone format conversion (+923XXXXXXXXX)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Client Application                    │
│              (Frontend / Mobile App)                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ HTTP/HTTPS
                     │
┌────────────────────┴────────────────────────────────────┐
│            FastAPI Backend (auth.py)                    │
│                                                          │
│  • /send-signup-otp                                     │
│  • /verify-signup-otp                                   │
│  • /forgot-password                                     │
│  • /verify-reset-otp                                    │
│  • /reset-password                                      │
│  • /login                                               │
│  • /profile                                             │
└────────────────┬────────────────┬───────────────────────┘
                 │                │
                 │                │
         ┌───────▼──────┐  ┌──────▼────────┐
         │  Twilio SDK  │  │  MongoDB      │
         │ (Verify Srvc)│  │  (Cosmos DB)  │
         └──────┬───────┘  └──────┬────────┘
                │                 │
         ┌──────▼────────┐  ┌─────▼────────┐
         │  Twilio API   │  │  Azure DB    │
         │  (OTP via SMS)│  │  (User Data) │
         └───────────────┘  └──────────────┘
```

## Environment Variables

### Required (.env file)

```env
# Twilio Configuration (Get from Twilio Console)
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_VERIFY_SERVICE_SID=your_verify_service_sid_here

# Azure Cosmos DB (Get from Azure Portal)
COSMOS_HOST=your_cosmos_host_here
COSMOS_USERNAME=your_cosmos_username_here
COSMOS_PASSWORD=your_cosmos_password_here
COSMOS_DB_NAME=shoptalk-cluster

# Azure OpenAI (Get from Azure OpenAI Dashboard)
AZURE_OPENAI_API_KEY=your_openai_api_key_here
AZURE_OPENAI_ENDPOINT=your_openai_endpoint_here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini

# JWT & Security (Generate random strings)
JWT_SECRET_KEY=generate_random_256_bit_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
REFRESH_TOKEN_EXPIRATION_DAYS=7

# Email Service (Optional - kept for future use)
SENDGRID_API_KEY=your_sendgrid_api_key_here
SENDGRID_FROM_EMAIL=your_email@example.com
```

⚠️ **IMPORTANT:** Replace all placeholder values with your actual credentials from:
- Twilio Console: https://console.twilio.com/
- Azure Portal: https://portal.azure.com/
- SendGrid Dashboard: https://app.sendgrid.com/

### Getting Twilio Credentials

#### 1. Twilio Account SID & Auth Token
1. Go to [Twilio Console](https://console.twilio.com/)
2. Copy your **Account SID** from the dashboard
3. Copy your **Auth Token** from the dashboard
4. Update `.env` with these values

#### 2. Twilio Verify Service SID

**Option A: Use Existing Service**
```
Currently using: VA12a601cc8def008d73e853f8b4c91e8f
```

**Option B: Create New Verify Service**
1. Log in to [Twilio Console](https://console.twilio.com/)
2. Navigate: Messaging → Verify → Services
3. Click "Create Verify Service"
4. Enter name: "ShopTalk AI"
5. Configure:
   - Default SMS Channel: Enabled
   - Friendly Name: ShopTalk Phone Verification
6. Copy the **Service SID** (starts with "VA")
7. Update `.env`:
   ```env
   TWILIO_VERIFY_SERVICE_SID=VA_your_service_sid
   ```

## Phone Number Format

### Pakistani Format Rules
- **Acceptable:** `03001234567`, `03121234567`, `03331234567`
- **Pattern:** Starts with `03` + 9 digits (11 digits total)
- **Regex:** `^03\d{9}$`

### Format Conversion (Automatic)
```python
# Input (Pakistani format)
phone = "03001234567"

# Conversion function (automatic in code)
international_phone = f"+92{phone[1:]}"
# Output: "+923001234567"
```

This conversion happens automatically in all endpoints. Users submit Pakistani format, backend converts for Twilio.

## API Endpoints

All endpoints are available at: `{BASE_URL}/api/auth/...`

For local testing: `http://localhost:8000/api/auth/...`  
For Render deployment: `https://your-app.onrender.com/api/auth/...`

### Signup Flow

**POST /send-signup-otp**
- Send OTP to phone for account creation
- Stores user data temporarily while awaiting OTP verification
- OTP validity: 10 minutes

**POST /verify-signup-otp**
- Verify OTP and create user account
- Returns access_token and refresh_token
- User is immediately logged in

### Login

**POST /login**
- Traditional phone + password authentication
- Returns access_token and refresh_token
- No OTP required (user already verified during signup)

**POST /login/token** (OAuth2 compatible)
- Alternative form for OAuth2 clients
- Same functionality as /login

### Password Reset Flow

**POST /forgot-password**
- Send password reset OTP to user's phone
- Does NOT reveal if user exists (security)

**POST /verify-reset-otp** (optional)
- Verify the reset OTP
- Can be combined with /reset-password in single request

**POST /reset-password**
- Reset password with valid OTP code
- Automatically verifies OTP before reset

### User Profile

**GET /profile**
- Requires: `Authorization: Bearer {access_token}`
- Returns: User object with all fields

## Database Schema

### User Collection

```json
{
  "_id": ObjectId("..."),
  "phone": "03001234567",           // Unique, primary identifier
  "email": "user@example.com",      // Required
  "name": "John Doe",                // Optional
  "hashed_password": "$2b$12...",   // bcrypt hash
  "phone_verified": true,            // Set after signup OTP verification
  "plan": "starter",                 // Subscription: starter, pro, enterprise
  "is_active": true,                 // Account status
  "ai_active": false,                // AI feature access
  "created_at": ISODate(...),       // Account creation timestamp
  "updated_at": ISODate(...)        // Last update timestamp
}
```

## Security Features

### Password Security
- **Hashing:** bcrypt with 10 rounds
- **Salt:** Automatically generated per password
- **Never stored:** Plain passwords never saved to database

### OTP Security
- **Validation:** Twilio Verify Service handles validation
- **Expiry:** 10 minutes (Twilio default)
- **Rate Limiting:** Max 3 verification attempts per OTP
- **Delivery:** SMS via Twilio (industry-standard encryption)

### Token Security
- **Type:** JWT (JSON Web Token)
- **Algorithm:** HS256
- **Access Token:** Valid for 30 minutes
- **Refresh Token:** Valid for 7 days
- **Signature:** Uses JWT_SECRET_KEY from .env
- **Header Format:** `Authorization: Bearer {token}`

### Account Security
- **Unique Phone:** Each phone number can only have one account
- **Email Validation:** Pydantic EmailStr validator
- **Phone Validation:** Custom Pakistani format validator
- **No Enumeration:** Forgot password doesn't reveal user existence

## Testing

### Prerequisites
- Backend running: `python -m uvicorn app.main:app --reload`
- Port: `8000` (default) or configured port
- Twilio account with SMS/Verify enabled
- Valid phone number to receive SMS

### Using Test Script

```bash
# Interactive mode (prompts for choices)
python test_phone_auth.py

# Quick connectivity test
python test_phone_auth.py --quick
```

### Manual cURL Testing

```bash
# 1. Send signup OTP
curl -X POST http://localhost:8000/api/auth/send-signup-otp \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "email": "test@example.com",
    "name": "Test User",
    "password": "TestPassword123!"
  }'

# 2. Verify OTP (after receiving SMS code)
curl -X POST http://localhost:8000/api/auth/verify-signup-otp \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "code": "123456"
  }'

# 3. Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "password": "TestPassword123!"
  }'

# 4. Get profile
curl -X GET http://localhost:8000/api/auth/profile \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

### Debugging OTP Issues

**Issue:** "OTP has expired"
- **Cause:** More than 10 minutes passed since OTP sent
- **Solution:** Request new OTP

**Issue:** "Invalid OTP code"
- **Cause:** Wrong code entered or OTP already verified
- **Solution:** Double-check code, request new OTP if needed

**Issue:** "No OTP found for this phone number"
- **Cause:** /send-signup-otp was not called first
- **Solution:** Call /send-signup-otp before /verify-signup-otp

**Issue:** "Failed to send OTP. Please check your phone number."
- **Cause:** Twilio API error (invalid credentials, service issue)
- **Solution:** 
  - Verify TWILIO_ACCOUNT_SID in .env
  - Verify TWILIO_AUTH_TOKEN in .env
  - Verify TWILIO_VERIFY_SERVICE_SID in .env
  - Check Twilio account status
  - Review Twilio error logs in console

## Deployment

### Requirements
- Python 3.8+
- FastAPI framework
- Twilio account (free tier sufficient for testing)
- Azure Cosmos DB instance
- Environment variables properly configured

### Render Deployment

The project includes a Dockerfile for containerization:

```bash
# Build Docker image
docker build -t shoptalkai-backend .

# Run container locally
docker run -p 8000:8000 \
  -e TWILIO_ACCOUNT_SID=your_sid \
  -e TWILIO_AUTH_TOKEN=your_token \
  -e TWILIO_VERIFY_SERVICE_SID=your_verify_sid \
  -e COSMOS_HOST=your_host \
  -e COSMOS_PASSWORD=your_password \
  -e JWT_SECRET_KEY=your_secret \
  shoptalkai-backend

# Deploy to Render.com:
# 1. Push to GitHub
# 2. Connect GitHub repo to Render
# 3. Define environment variables in Render dashboard
# 4. Deploy will automatically use Dockerfile
```

### Environment Variables in Render

Set these in Render Dashboard → Environment:
```
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_VERIFY_SERVICE_SID
COSMOS_HOST
COSMOS_USERNAME
COSMOS_PASSWORD
COSMOS_DB_NAME
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_DEPLOYMENT_NAME
JWT_SECRET_KEY
JWT_ALGORITHM
JWT_EXPIRATION_HOURS
REFRESH_TOKEN_EXPIRATION_DAYS
```

### Health Check

Test deployed backend:
```bash
curl https://your-app.onrender.com/docs
```

If available, Swagger UI shows all endpoints at: `/docs`

## Code Changes Summary

### Modified Files

**app/routers/auth.py**
- Replaced email-based models with phone-based models
- Removed email password reset endpoints
- Added 5 new Twilio Verify Service endpoints
- Removed SendGrid email functions
- Updated signup endpoint to require OTP verification
- Added in-memory signup OTP tracking

**app/core/config.py**
- Added `TWILIO_VERIFY_SERVICE_SID` setting
- Settings now support full Twilio Verify integration

**app/models/user.py**
- Added `phone_verified` field to UserInDB and UserResponse
- Added Pakistani phone validation decorator
- Email field marked as required

**.env**
- Added `TWILIO_VERIFY_SERVICE_SID` configuration
- Updated Twilio section comments

### New Files

**PHONE_AUTH_ENDPOINTS.md**
- Comprehensive endpoint documentation
- Request/response examples
- Error handling guide

**test_phone_auth.py**
- Interactive test script
- Manual endpoint testing
- Debugging assistance

**SETUP_AND_DEPLOYMENT.md** (this file)
- Implementation guide
- Deployment instructions
- Configuration reference

## Troubleshooting

### Common Issues

**1. "TWILIO_VERIFY_SERVICE_SID not found"**
```
Error: 'TWILIO_VERIFY_SERVICE_SID' not found in settings
```
- Check `.env` file has TWILIO_VERIFY_SERVICE_SID
- Ensure value starts with "VA"
- Restart application after updating .env

**2. "Invalid authentication credentials"**
```
Error: Invalid authentication credentials
Status Code: 401
```
- Verify TWILIO_ACCOUNT_SID is correct
- Verify TWILIO_AUTH_TOKEN is correct
- Check credentials in Twilio Console

**3. "Service not found"**
```
Error: Verify Service not found
Status Code: 404
```
- Verify TWILIO_VERIFY_SERVICE_SID is correct
- Service may have been deleted
- Create new Verify Service if needed

**4. "SMS delivery failed"**
```
Error: Failed to send OTP. Please check your phone number.
```
- Check phone number format (must be 03XXXXXXXXX)
- Verify phone is in SMS-supported country
- Check Twilio account SMS credits/balance

**5. "Database connection error"**
```
Error: Could not connect to MongoDB
```
- Verify COSMOS_HOST, COSMOS_USERNAME, COSMOS_PASSWORD
- Check Azure Cosmos DB is running
- Verify network connectivity to Azure

### Logs and Debugging

#### Check Backend Logs
```bash
# Development mode with logs
python -m uvicorn app.main:app --reload --log-level debug

# Production Render logs
# View in Render dashboard → Logs
```

#### Check Twilio Logs
1. Go to Twilio Console
2. Monitoring → Logs
3. Filter by Verify Service
4. Check for failed verification attempts

#### Phone Format Validation
```python
# Test Pakistani phone validation
import re

phone = "03001234567"
pattern = r"^03\d{9}$"

if re.match(pattern, phone):
    print("Valid Pakistani phone")
else:
    print("Invalid format")
```

## Performance & Limits

### Rate Limits
- OTP requests: No hard limit (Twilio default)
- Verification attempts: 3 per OTP code
- Account creation: Not limited
- Login attempts: Not rate limited (implement in production)

### Timeouts
- Express API calls: 30 seconds (default)
- Database queries: 30 seconds (default)
- Twilio SMS delivery: 2-5 seconds typically
- OTP validity: 10 minutes

### Scalability
- Phone-based auth stores minimal state
- Twilio handles OTP delivery at scale
- Database: Azure Cosmos DB auto-scales
- No in-memory OTP storage (except temp signup data)

## Best Practices

### For Users
1. ✅ Use real phone number to receive SMS
2. ✅ Enter OTP within 10 minutes
3. ✅ Keep password secure (12+ chars recommended)
4. ✅ Use access tokens, not credentials, for API calls
5. ✅ Refresh tokens when they expire

### For Developers
1. ✅ Always validate phone format before API call
2. ✅ Implement client-side retry logic for failed OTP
3. ✅ Store tokens securely (localStorage, secure cookie)
4. ✅ Never log or expose access/refresh tokens
5. ✅ Implement logout to clean up tokens
6. ✅ Use HTTPS in production

### For Operations
1. ✅ Monitor Twilio SMS send rates
2. ✅ Set up Twilio cost alerts
3. ✅ Monitor database connection pool
4. ✅ Implement API rate limiting middleware
5. ✅ Set up alerting for auth endpoint errors
6. ✅ Regular security audits

## Support & Documentation

### Official Documentation
- [Twilio Verify API Docs](https://www.twilio.com/docs/verify/api)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [MongoDB/Motor Async Driver](https://motor.readthedocs.io/)

### Project Documentation
- `PHONE_AUTH_ENDPOINTS.md` - API endpoint reference
- `Dockerfile` - Container configuration
- `.env` - Environment variables template

### Local Testing
```bash
# Install dependencies
pip install -r requirements.txt

# Run backend
python -m uvicorn app.main:app --reload

# Run tests
python test_phone_auth.py

# Check syntax
python -m py_compile app/routers/auth.py
```

## Changelog

### v1.0.0 - Phone-Based Twilio Verify Integration
- ✅ Replaced email-based password reset with phone-based OTP
- ✅ Integrated Twilio Verify Service for managed OTP delivery
- ✅ Added signup OTP verification flow
- ✅ Updated user model with phone_verified field
- ✅ Added Pakistani phone number validation
- ✅ Created comprehensive testing script
- ✅ Complete API documentation
- ✅ Setup and deployment guide

### Previous Versions
- v0.9.0 - Email-based password reset with SendGrid
- v0.8.0 - Basic JWT authentication
- v0.7.0 - Initial FastAPI setup

## License

This implementation is part of the ShopTalk AI project and follows the project's license terms.

## Questions?

For issues or questions:
1. Check troubleshooting section above
2. Review Twilio documentation
3. Check backend logs
4. Test with manual cURL commands
5. Contact development team

---

**Last Updated:** 2024
**Status:** Production Ready
**Twilio SDK Version:** 8.1.0
**FastAPI Version:** 0.109.2
