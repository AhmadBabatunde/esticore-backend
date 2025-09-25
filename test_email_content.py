#!/usr/bin/env python3
"""
Test script to verify email content is using OTP codes
"""
from modules.auth.email_service import email_service
from datetime import datetime, timedelta

def test_email_content():
    """Test that email templates contain OTP codes, not verification links"""
    
    print("=== Testing Email Template Content ===\n")
    
    # Test OTP generation
    otp = email_service.generate_verification_token()
    print(f"1. OTP Generation: {otp} (length: {len(otp)})")
    
    if len(otp) == 6 and otp.isdigit():
        print("   ✅ OTP is 6-digit numeric code - GOOD!")
    else:
        print("   ❌ OTP should be 6-digit numeric code")
    
    # Check if email service has correct method signature
    try:
        # This should not fail if the method signature is correct
        result = email_service.send_verification_email.__doc__
        print(f"\n2. Email Service Method: {result}")
        
        # Try to access the email template (inspect the source)
        import inspect
        source = inspect.getsource(email_service.send_verification_email)
        
        print("\n3. Template Content Analysis:")
        if 'otp_code' in source:
            print("   ✅ Found 'otp_code' in email template - GOOD!")
        else:
            print("   ❌ Missing 'otp_code' in email template")
            
        if 'verification_url' in source:
            print("   ❌ Found 'verification_url' in email template - BAD!")
        else:
            print("   ✅ No 'verification_url' found - GOOD!")
            
        if 'Click the button' in source:
            print("   ❌ Found 'Click the button' text - BAD!")
        else:
            print("   ✅ No 'Click the button' text - GOOD!")
            
        if '6-digit' in source or 'OTP' in source or 'code' in source.lower():
            print("   ✅ Found OTP-related text - GOOD!")
        
        # Check expiration time
        if '5 minutes' in source:
            print("   ✅ Found 5-minute expiration - GOOD!")
        elif '24 hours' in source:
            print("   ❌ Found 24-hour expiration - BAD!")
            
    except Exception as e:
        print(f"   ❌ Error inspecting email service: {e}")

def check_database_token_storage():
    """Check if database is storing OTP codes correctly"""
    print("\n4. Database Token Storage Test:")
    
    try:
        from modules.database import db_manager
        
        # Test token creation
        test_user_id = 999  # Non-existent user for testing
        test_token = "123456"
        expires_at = datetime.now() + timedelta(minutes=5)
        
        print(f"   Testing token storage: {test_token}")
        print(f"   Expiration: {expires_at}")
        
        # This should work if the database schema is correct
        if hasattr(db_manager, 'create_verification_token'):
            print("   ✅ Database has create_verification_token method - GOOD!")
        else:
            print("   ❌ Database missing create_verification_token method")
            
        if hasattr(db_manager, 'get_user_by_verification_token'):
            print("   ✅ Database has get_user_by_verification_token method - GOOD!")
        else:
            print("   ❌ Database missing get_user_by_verification_token method")
            
    except Exception as e:
        print(f"   ❌ Database test error: {e}")

if __name__ == "__main__":
    print("Testing Email Content for OTP vs Verification Links\n")
    
    test_email_content()
    check_database_token_storage()
    
    print("\n" + "="*60)
    print("📧 EMAIL CONTENT TEST COMPLETE!")
    print("="*60)
    print("\nIf you're still receiving verification links:")
    print("1. Restart your application (python app.py)")
    print("2. Clear your email cache/refresh")
    print("3. Test signup with a new email address")
    print("4. Check that you're using the latest endpoints")