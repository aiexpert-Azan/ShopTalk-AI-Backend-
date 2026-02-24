# Phone-Based Authentication Endpoints (Twilio Verify Service)

## Overview
This backend now uses **Twilio Verify Service** for all phone-based OTP authentication. All endpoints require Pakistani phone numbers in the format **03XXXXXXXXX** (11 digits starting with 03).

## Authentication Flow

### 1. Signup with Phone OTP Verification

**Step 1: Request OTP for Signup**
```
POST /api/auth/send-signup-otp
Content-Type: application/json

{
  "phone": "03001234567",
  "email": "user@example.com",
  "name": "John Doe",
  "password": "YourSecurePassword123!"
}
```

**Response (201 Created):**
```json
{
  "message": "OTP sent to your phone. It expires in 10 minutes.",
  "phone": "03001234567"
}
```

**Step 2: Verify OTP and Create Account**
```
POST /api/auth/verify-signup-otp
Content-Type: application/json

{
  "phone": "03001234567",
  "code": "123456"
}
```

**Response (201 Created):**
```json
{
  "message": "Phone verified successfully. User created.",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### 2. Login with Existing Account

**Option A: Form-based Login (OAuth2 Compatible)**
```
POST /api/auth/login/token
Content-Type: application/x-www-form-urlencoded

username=03001234567&password=YourSecurePassword123!
```

**Option B: JSON-based Login**
```
POST /api/auth/login
Content-Type: application/json

{
  "phone": "03001234567",
  "password": "YourSecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### 3. Password Reset with Phone OTP

**Step 1: Request Password Reset OTP**
```
POST /api/auth/forgot-password
Content-Type: application/json

{
  "phone": "03001234567"
}
```

**Response (200 OK):**
```json
{
  "message": "OTP sent to your phone. It expires in 10 minutes.",
  "phone": "03001234567"
}
```

**Note:** If the phone number doesn't exist in the database, the response is the same for security reasons (no account enumeration).

**Step 2: Verify Reset OTP (Optional - for confirmation)**
```
POST /api/auth/verify-reset-otp
Content-Type: application/json

{
  "phone": "03001234567",
  "code": "123456"
}
```

**Response (200 OK):**
```json
{
  "message": "OTP verified successfully",
  "phone": "03001234567"
}
```

**Step 3: Reset Password with Verified OTP**
```
POST /api/auth/reset-password
Content-Type: application/json

{
  "phone": "03001234567",
  "code": "123456",
  "new_password": "NewSecurePassword456!"
}
```

**Response (200 OK):**
```json
{
  "message": "Password reset successfully",
  "phone": "03001234567"
}
```

---

### 4. Get User Profile

**Request:**
```
GET /api/auth/profile
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "phone": "03001234567",
  "email": "user@example.com",
  "name": "John Doe",
  "phone_verified": true,
  "plan": "starter",
  "is_active": true,
  "ai_active": false
}
```

---

## Error Responses

### Invalid Phone Format (400 Bad Request)
```json
{
  "detail": "Please enter a valid Pakistani mobile number starting with 03 (11 digits)"
}
```

### Invalid OTP (400 Bad Request)
```json
{
  "detail": "Invalid OTP code. Please try again."
}
```

### OTP Expired (400 Bad Request)
```json
{
  "detail": "OTP has expired. Please request a new one."
}
```

### User Not Found (404 Not Found)
```json
{
  "detail": "User not found"
}
```

### Twilio Service Error (500 Internal Server Error)
```json
{
  "detail": "Failed to send OTP. Please check your phone number."
}
```

---

## Technical Details

### Phone Format Conversion
- **Input Format:** `03XXXXXXXXX` (11 digits, Pakistani format)
- **Twilio Format:** `+923XXXXXXXXX` (International format)
- **Conversion Logic:** `+92` + phone[1:] (removes leading 0)

### Twilio Verify Service
- **Service Type:** Managed OTP delivery (SMS)
- **OTP Validity:** 10 minutes (Twilio default)
- **OTP Length:** 6 digits (Twilio default)
- **Max Attempts:** 3 per OTP code (Twilio default)

### Database Fields
- `phone` (String, 11 digits): Unique identifier
- `email` (String, required): User's email address
- `name` (String, optional): User's name
- `hashed_password` (String): bcrypt-hashed password
- `phone_verified` (Boolean): Set to `true` after successful signup/OTP verification
- `plan` (String, default: "starter"): User's subscription plan
- `is_active` (Boolean, default: true): Account status
- `ai_active` (Boolean, default: false): AI feature activation status
- `created_at` (DateTime): Account creation timestamp

### Configuration Required
Add to `.env` file:
```env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_VERIFY_SERVICE_SID=your_verify_service_sid
```

To get `TWILIO_VERIFY_SERVICE_SID`:
1. Log in to [Twilio Console](https://console.twilio.com/)
2. Navigate to: Messaging → Verify → Services
3. Click on your service or create a new one
4. Copy the "Service SID" (starts with "VA")

---

## Implementation Notes

### Signup Flow
1. Client calls `/send-signup-otp` - OTP sent via SMS, user data stored temporarily
2. Client calls `/verify-signup-otp` - Twilio verifies OTP, user created in DB, tokens returned
3. User is immediately logged in with access/refresh tokens

### Password Reset Flow
1. Client calls `/forgot-password` - OTP sent via SMS
2. Client calls `/verify-reset-otp` - OTP verified (optional but recommended)
3. Client calls `/reset-password` - Password updated in DB after OTP verification

### Token Management
- **Access Token:** Valid for 30 minutes (configurable)
- **Refresh Token:** Used to get new access tokens
- Both tokens are JWT-encoded and contain the user's phone number

### Security Features
- Passwords hashed with bcrypt (10 rounds)
- OTP validation via Twilio's managed service
- Phone number verification required for account creation
- No account enumeration (forgot-password doesn't reveal user existence)
- Tokens require `Authorization: Bearer <token>` header

---

## Testing

### Example Test Sequence
```bash
# 1. Request signup OTP
curl -X POST http://localhost:8000/api/auth/send-signup-otp \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "email": "test@example.com",
    "name": "Test User",
    "password": "TestPassword123!"
  }'

# Response: OTP sent message

# 2. Verify signup OTP (wait for SMS and use the code)
curl -X POST http://localhost:8000/api/auth/verify-signup-otp \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "code": "123456"
  }'

# Response: access_token and refresh_token

# 3. Get user profile (using access token)
curl -X GET http://localhost:8000/api/auth/profile \
  -H "Authorization: Bearer <access_token>"

# 4. Login with phone and password
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "password": "TestPassword123!"
  }'

# 5. Request password reset
curl -X POST http://localhost:8000/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"phone": "03001234567"}'

# 6. Verify reset OTP
curl -X POST http://localhost:8000/api/auth/verify-reset-otp \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "code": "654321"
  }'

# 7. Reset password
curl -X POST http://localhost:8000/api/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "03001234567",
    "code": "654321",
    "new_password": "NewPassword456!"
  }'
```

---

## Endpoint Summary Table

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| /signup | POST | Create account (old - requires OTP via /send-signup-otp first) | No |
| /send-signup-otp | POST | Send OTP for account creation | No |
| /verify-signup-otp | POST | Verify OTP and create account | No |
| /login | POST | Login with phone/password | No |
| /login/token | POST | Login with phone/password (OAuth2) | No |
| /forgot-password | POST | Request password reset OTP | No |
| /verify-reset-otp | POST | Verify password reset OTP | No |
| /reset-password | POST | Reset password with verified OTP | No |
| /profile | GET | Get authenticated user's profile | Yes |

---

## Removed Endpoints

The following email-based endpoints have been **removed** in favor of phone-based Twilio Verify:
- ~~POST /forgot-password~~ (email-based)
- ~~POST /verify-reset-code~~ (email-based)
- ~~POST /reset-password~~ (email-based - old implementation)
- ~~POST /send-otp~~ (custom SMS implementation)
- ~~POST /verify-otp~~ (custom OTP storage)

All functionality has been replaced with **Twilio Verify Service** for better reliability and security.

---

## Changelog

### Latest Changes (Phone-Based Twilio Verify)
- ✅ Replaced email-based password reset with phone-based OTP
- ✅ Integrated Twilio Verify Service (managed OTP delivery)
- ✅ Added `/send-signup-otp` endpoint for account creation with OTP
- ✅ Added `/verify-signup-otp` endpoint for account creation verification
- ✅ Added `/forgot-password` endpoint (phone-based, Twilio Verify)
- ✅ Added `/verify-reset-otp` endpoint for password reset verification
- ✅ Added `/reset-password` endpoint with OTP verification
- ✅ Removed old email-based password reset functions
- ✅ Removed custom in-memory OTP storage (Twilio manages it)
- ✅ Updated user model with `phone_verified` field
- ✅ Updated configuration with `TWILIO_VERIFY_SERVICE_SID`

### Previous Changes (Email-Based)
- ✅ SendGrid integration for email delivery
- ✅ Custom 6-digit code generation
- ✅ In-memory storage with 10-minute expiry
- ✅ Email templates with HTML formatting

---

## Future Enhancements

Potential improvements for future versions:
- [ ] Resend OTP functionality (with rate limiting)
- [ ] OTP delivery method selection (SMS, WhatsApp, etc.)
- [ ] Account lockout after failed OTP attempts
- [ ] Phone number change verification
- [ ] Multi-device token management
- [ ] Biometric authentication integration
- [ ] Audit logging for authentication events
- [ ] IP-based suspicious activity detection
