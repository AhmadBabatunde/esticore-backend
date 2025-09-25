# Simple Postman Tests for OTP Verification System

## 🔢 **OTP System Overview**

Instead of verification links, users now receive **6-digit OTP codes** that expire in **5 minutes**.

---

## 🚀 **Quick Postman Test Sequence**

### Test 1: Signup (Sends OTP Email)
**Method:** `POST`  
**URL:** `http://localhost:8000/auth/signup`  
**Headers:**
```
Content-Type: application/x-www-form-urlencoded
```
**Body (form-data):**
```
firstname: OTP
lastname: Test
email: your-email@example.com
password: testpass123
confirm_password: testpass123
```
**Expected Response (200):**
```json
{
  "message": "User created successfully. Please check your email to verify your account.",
  "user_id": 1,
  "email": "your-email@example.com",
  "verification_email_sent": true,
  "requires_verification": true
}
```

---

### Test 2: Login Before Verification (Resends OTP)
**Method:** `POST`  
**URL:** `http://localhost:8000/auth/login`  
**Headers:**
```
Content-Type: application/x-www-form-urlencoded
```
**Body (form-data):**
```
email: your-email@example.com
password: testpass123
```
**Expected Response (200):**
```json
{
  "message": "Please verify your email address before logging in. We've sent a new verification email.",
  "user_id": 1,
  "email": "your-email@example.com",
  "requires_verification": true,
  "verified": false,
  "verification_email_sent": true
}
```

---

### Test 3: Invalid OTP Verification
**Method:** `POST`  
**URL:** `http://localhost:8000/auth/verify-otp`  
**Headers:**
```
Content-Type: application/x-www-form-urlencoded
```
**Body (form-data):**
```
email: your-email@example.com
otp: 000000
```
**Expected Response (400):**
```json
{
  "detail": "Invalid verification code"
}
```

---

### Test 4: Valid OTP Verification ⭐
**Method:** `POST`  
**URL:** `http://localhost:8000/auth/verify-otp`  
**Headers:**
```
Content-Type: application/x-www-form-urlencoded
```
**Body (form-data):**
```
email: your-email@example.com
otp: 123456
```
*Replace `123456` with the actual 6-digit code from your email*

**Expected Response (200):**
```json
{
  "message": "Email verified successfully! You can now log in.",
  "user_id": 1,
  "email": "your-email@example.com",
  "verified": true
}
```

---

### Test 5: Login After Verification (Should Work)
**Method:** `POST`  
**URL:** `http://localhost:8000/auth/login`  
**Headers:**
```
Content-Type: application/x-www-form-urlencoded
```
**Body (form-data):**
```
email: your-email@example.com
password: testpass123
```
**Expected Response (200):**
```json
{
  "message": "Login successful",
  "user_id": 1,
  "firstname": "OTP",
  "lastname": "Test",
  "email": "your-email@example.com",
  "verified": true
}
```

---

### Test 6: Resend OTP
**Method:** `POST`  
**URL:** `http://localhost:8000/auth/resend-verification`  
**Headers:**
```
Content-Type: application/x-www-form-urlencoded
```
**Body (form-data):**
```
email: your-email@example.com
```
**Expected Response (200):**
```json
{
  "message": "Verification email sent successfully",
  "email": "your-email@example.com",
  "email_sent": true
}
```

---

## 📧 **Email Format**

Users will receive emails like this:

```
Subject: Your Verification Code - Esticore
From: Esticore <noreply@esticore.com>

Hi OTP!

Your verification code is:

   1 2 3 4 5 6

⚠️ Important: This code expires in 5 minutes.
```

---

## 🔧 **Key Differences from Link-Based Verification**

| **Link-Based (Old)** | **OTP-Based (New)** |
|----------------------|---------------------|
| Long verification URLs | 6-digit codes |
| 24-hour expiration | 5-minute expiration |
| Click verification | Manual code entry |
| GET /auth/verify?token=UUID | POST /auth/verify-otp |

---

## ⚠️ **Important Notes**

1. **OTP expires in 5 minutes** - Test quickly after receiving email
2. **Use your real email** - You need to receive the actual OTP code
3. **Legacy support** - Old verification links still work for existing tokens
4. **Automatic resend** - Login attempts automatically send new OTP codes
5. **Case sensitive** - OTP codes are numeric only (6 digits)

---

## 🧪 **Testing Tips**

1. **Set up email** - Configure SMTP settings in `.env` file first
2. **Use real email** - You need to receive actual OTP codes
3. **Test timing** - Try expired OTP by waiting 6+ minutes
4. **Test resend** - Multiple login attempts should send new codes
5. **Frontend ready** - Use POST `/auth/verify-otp` endpoint

The OTP system provides better security with shorter expiration times and easier user experience with simple 6-digit codes! 🎉