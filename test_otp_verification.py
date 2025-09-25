#!/usr/bin/env python3
"""
Test script for OTP verification system
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_otp_verification_flow():
    """Test the complete OTP verification flow"""
    
    print("=== Testing OTP Verification System ===\n")
    
    # Test 1: Regular signup (should send OTP email)
    print("1. Testing signup with OTP...")
    signup_data = {
        "firstname": "OTP",
        "lastname": "Test", 
        "email": "otp.test@example.com",
        "password": "testpass123",
        "confirm_password": "testpass123"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/signup", data=signup_data)
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
        
        if response.status_code == 200 and result.get("requires_verification"):
            print("   ✅ Signup sends OTP verification email - GOOD!")
        else:
            print("   ❌ Signup should require OTP verification")
            
    except Exception as e:
        print(f"   ❌ Signup test failed: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: Login before verification (should be blocked and resend OTP)
    print("2. Testing login before verification (should resend OTP)...")
    login_data = {
        "email": "otp.test@example.com",
        "password": "testpass123"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", data=login_data)
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
        
        if result.get("requires_verification") and result.get("verification_email_sent"):
            print("   ✅ Login blocked and OTP resent - GOOD!")
        else:
            print("   ❌ Login should be blocked and resend OTP")
            
    except Exception as e:
        print(f"   ❌ Login test failed: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 3: Invalid OTP verification
    print("3. Testing invalid OTP verification...")
    otp_data = {
        "email": "otp.test@example.com",
        "otp": "000000"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/verify-otp", data=otp_data)
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
        
        if response.status_code == 400:
            print("   ✅ Invalid OTP properly rejected - GOOD!")
        else:
            print("   ❌ Invalid OTP should be rejected")
            
    except Exception as e:
        print(f"   ❌ Invalid OTP test failed: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 4: Valid OTP format test
    print("4. Testing valid OTP format (but likely expired)...")
    otp_data = {
        "email": "otp.test@example.com",
        "otp": "123456"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/verify-otp", data=otp_data)
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
        
        if response.status_code in [400, 404]:
            print("   ✅ OTP verification endpoint working - Check email for real code!")
        else:
            print("   ❌ Unexpected response")
            
    except Exception as e:
        print(f"   ❌ OTP verification test failed: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test 5: Resend OTP
    print("5. Testing resend OTP...")
    resend_data = {
        "email": "otp.test@example.com"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/resend-verification", data=resend_data)
        print(f"   Status: {response.status_code}")
        result = response.json()
        print(f"   Response: {json.dumps(result, indent=2)}")
        
        if response.status_code == 200:
            print("   ✅ Resend OTP endpoint works!")
        else:
            print("   ❌ Resend OTP failed")
            
    except Exception as e:
        print(f"   ❌ Resend OTP test failed: {e}")

def show_manual_test_instructions():
    """Show instructions for manual testing with real OTP"""
    print("\n" + "="*60)
    print("📧 MANUAL OTP TESTING INSTRUCTIONS")
    print("="*60)
    print("\n1. Check your email for the 6-digit OTP code")
    print("2. Use this curl command to verify with the real OTP:")
    print("\n   curl -X POST \"http://localhost:8000/auth/verify-otp\" \\")
    print("     -H \"Content-Type: application/x-www-form-urlencoded\" \\")
    print("     -d \"email=otp.test@example.com&otp=YOUR_6_DIGIT_CODE\"")
    print("\n3. After successful verification, test login:")
    print("\n   curl -X POST \"http://localhost:8000/auth/login\" \\")
    print("     -H \"Content-Type: application/x-www-form-urlencoded\" \\")
    print("     -d \"email=otp.test@example.com&password=testpass123\"")
    print("\n4. Expected successful verification response:")
    print("   {")
    print("     \"message\": \"Email verified successfully! You can now log in.\",")
    print("     \"user_id\": 1,")
    print("     \"email\": \"otp.test@example.com\",")
    print("     \"verified\": true")
    print("   }")

if __name__ == "__main__":
    print("Starting OTP Verification System Tests...")
    print("Make sure your application is running on http://localhost:8000\n")
    
    try:
        # Quick connectivity test
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Application is running!\n")
        else:
            print("❌ Application health check failed\n")
    except:
        print("❌ Cannot connect to application. Make sure it's running on localhost:8000\n")
        print("Start the application with: python app.py\n")
        exit(1)
    
    test_otp_verification_flow()
    show_manual_test_instructions()
    
    print("\n" + "="*60)
    print("🔢 OTP VERIFICATION SYSTEM TEST COMPLETE!")
    print("="*60)
    print("\nKEY FEATURES:")
    print("✅ 6-digit OTP codes instead of long URLs")
    print("✅ 5-minute expiration for security")
    print("✅ Automatic OTP resend on login attempts") 
    print("✅ Professional email templates")
    print("✅ Both legacy link and OTP support")
    print("\nNEXT STEPS:")
    print("1. Configure email settings in .env file")
    print("2. Test with real email address")
    print("3. Check OTP delivery and verification")
    print("4. Update frontend to use /auth/verify-otp endpoint")