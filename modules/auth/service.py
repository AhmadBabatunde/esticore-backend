"""
Authentication services for the Floor Plan Agent API
"""
import secrets
from typing import Optional, Dict, Any
from datetime import datetime
from email_validator import validate_email, EmailNotValidError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from fastapi import HTTPException

from modules.config.settings import settings
from modules.database import db_manager, User

class AuthService:
    """Authentication service class"""
    
    def __init__(self):
        self.db = db_manager
    
    def validate_email_format(self, email: str) -> bool:
        """Validate email format"""
        try:
            # Skip deliverability checks for testing
            validate_email(email, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False
    
    def validate_password_strength(self, password: str) -> tuple[bool, str]:
        """Validate password strength"""
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            return False, f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long"
        return True, ""
    
    def signup_user(self, firstname: str, lastname: str, email: str, password: str, confirm_password: str) -> Dict[str, Any]:
        """Regular signup process"""
        # Validate email format
        if not self.validate_email_format(email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Validate password confirmation
        if password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        
        # Validate password strength
        is_valid, error_msg = self.validate_password_strength(password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Check if email already exists
        existing_user = self.db.get_user_by_email(email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")
        
        # Create new user
        try:
            user_id = self.db.create_user(firstname, lastname, email, password)
            
            # Send verification email
            from modules.auth.email_service import email_service
            email_sent = email_service.send_verification_email(user_id, email, firstname)
            
            return {
                "message": "User created successfully. Please check your email to verify your account.",
                "user_id": user_id,
                "firstname": firstname,
                "lastname": lastname,
                "email": email,
                "verification_email_sent": email_sent,
                "requires_verification": True
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Regular login process with email verification check"""
        # Validate email format
        if not self.validate_email_format(email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Verify credentials
        user = self.db.verify_user_credentials(email, password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Check if email is verified (except for Google OAuth users)
        if not user.is_verified and not user.google_id:
            # Automatically resend verification email
            from modules.auth.email_service import email_service
            email_sent = email_service.resend_verification_email(user.id, user.email, user.firstname)
            
            return {
                "message": "Please verify your email address before logging in. We've sent a new verification email.",
                "user_id": user.id,
                "email": user.email,
                "requires_verification": True,
                "verified": False,
                "verification_email_sent": email_sent
            }
        
        return {
            "message": "Login successful",
            "user_id": user.id,
            "firstname": user.firstname,
            "lastname": user.lastname,
            "email": user.email,
            "verified": user.is_verified
        }
    
    def google_signup(self, id_token_str: str) -> Dict[str, Any]:
        """Google OAuth signup process"""
        print(f"DEBUG: Google signup called with token: {id_token_str[:50]}...")
        print(f"DEBUG: GOOGLE_CLIENT_ID configured: {bool(settings.GOOGLE_CLIENT_ID)}")
        
        if not settings.GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
        # Validate that the token looks like a JWT (starts with 'eyJ')
        if not id_token_str.startswith('eyJ'):
            raise HTTPException(status_code=400, detail="Invalid ID token format. Expected JWT token starting with 'eyJ'")
        
        try:
            # Verify the Google ID token
            print(f"DEBUG: Attempting to verify token with client ID: {settings.GOOGLE_CLIENT_ID[:20]}...")
            idinfo = id_token.verify_oauth2_token(id_token_str, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
            print(f"DEBUG: Token verified successfully. User info: {idinfo.get('email', 'no_email')}")
            
            # Extract user information from Google
            google_user_id = idinfo['sub']
            email = idinfo['email']
            firstname = idinfo.get('given_name', '')
            lastname = idinfo.get('family_name', '')
            
            print(f"DEBUG: Extracted info - email: {email}, name: {firstname} {lastname}")
            
            # Check if user already exists with this email
            existing_user = self.db.get_user_by_email(email)
            if existing_user:
                raise HTTPException(status_code=400, detail="User with this email already exists")
            
            # Check if Google ID already exists
            existing_google_user = self.db.get_user_by_google_id(google_user_id)
            if existing_google_user:
                raise HTTPException(status_code=400, detail="Google account already linked to another user")
            
            # Create new user with Google OAuth
            # Generate a random password since they're using Google OAuth
            random_password = secrets.token_urlsafe(32)
            
            user_id = self.db.create_user(firstname, lastname, email, random_password, google_user_id)
            
            # Mark Google OAuth users as verified by default
            self.db.verify_user_email(user_id)
            
            return {
                "message": "User created successfully",
                "user_id": user_id,
                "firstname": firstname,
                "lastname": lastname,
                "email": email,
                "verified": True,
                "action": "signup"
            }
            
        except ValueError as e:
            # Invalid token
            print(f"DEBUG: Token validation failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid Google ID token: {str(e)}")
        except Exception as e:
            print(f"DEBUG: General error in google_signup: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Google signup error: {str(e)}")
    
    def google_signin(self, id_token_str: str) -> Dict[str, Any]:
        """Google OAuth signin process"""
        print(f"DEBUG: Google signin called with token: {id_token_str[:50]}...")
        print(f"DEBUG: GOOGLE_CLIENT_ID configured: {bool(settings.GOOGLE_CLIENT_ID)}")
        
        if not settings.GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
        # Validate that the token looks like a JWT (starts with 'eyJ')
        if not id_token_str.startswith('eyJ'):
            raise HTTPException(status_code=400, detail="Invalid ID token format. Expected JWT token starting with 'eyJ'")
        
        try:
            # Verify the Google ID token
            print(f"DEBUG: Attempting to verify token with client ID: {settings.GOOGLE_CLIENT_ID[:20]}...")
            idinfo = id_token.verify_oauth2_token(id_token_str, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
            print(f"DEBUG: Token verified successfully. User info: {idinfo.get('email', 'no_email')}")
            
            # Extract user information from Google
            google_user_id = idinfo['sub']
            email = idinfo['email']
            
            # Find user by Google ID first, then by email
            user = self.db.get_user_by_google_id(google_user_id)
            if not user:
                user = self.db.get_user_by_email(email)
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found. Please sign up first.")
            
            # If user exists but doesn't have Google ID linked, link it
            if user.google_id is None:
                self.db.update_user_google_id(user.id, google_user_id)
            
            return {
                "message": "Login successful",
                "user_id": user.id,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "email": user.email
            }
            
        except ValueError as e:
            # Invalid token
            print(f"DEBUG: Token validation failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid Google ID token: {str(e)}")
        except Exception as e:
            print(f"DEBUG: General error in google_signin: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Google signin error: {str(e)}")
    
    def google_signin_userinfo(self, email: str, google_id: str) -> Dict[str, Any]:
        """Google OAuth signin process using user info"""
        print(f"DEBUG: Google signin userinfo called for email: {email}, google_id: {google_id[:20]}...")
        
        try:
            # Find user by Google ID first, then by email
            user = self.db.get_user_by_google_id(google_id)
            if not user:
                user = self.db.get_user_by_email(email)
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found. Please sign up first.")
            
            # If user exists but doesn't have Google ID linked, link it
            if user.google_id is None:
                self.db.update_user_google_id(user.id, google_id)
            
            return {
                "message": "Login successful",
                "user_id": user.id,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "email": user.email
            }
            
        except Exception as e:
            print(f"DEBUG: General error in google_signin_userinfo: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Google signin error: {str(e)}")
    
    def google_signup_userinfo(self, email: str, firstname: str, lastname: str, google_id: str) -> Dict[str, Any]:
        """Google OAuth signup process using user info"""
        print(f"DEBUG: Google signup userinfo called for email: {email}, name: {firstname} {lastname}")
        
        try:
            # Validate email format
            if not self.validate_email_format(email):
                raise HTTPException(status_code=400, detail="Invalid email format")
            
            # Check if user already exists with this email
            existing_user = self.db.get_user_by_email(email)
            if existing_user:
                raise HTTPException(status_code=400, detail="User with this email already exists")
            
            # Check if Google ID already exists
            existing_google_user = self.db.get_user_by_google_id(google_id)
            if existing_google_user:
                raise HTTPException(status_code=400, detail="Google account already linked to another user")
            
            # Create new user with Google OAuth
            # Generate a random password since they're using Google OAuth
            random_password = secrets.token_urlsafe(32)
            
            user_id = self.db.create_user(firstname, lastname, email, random_password, google_id)
            
            return {
                "message": "User created successfully",
                "user_id": user_id,
                "firstname": firstname,
                "lastname": lastname,
                "email": email
            }
            
        except Exception as e:
            print(f"DEBUG: General error in google_signup_userinfo: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Google signup error: {str(e)}")
    
    def verify_email(self, token: str) -> Dict[str, Any]:
        """Verify user email using verification token"""
        try:
            # Find user by verification token
            user = self.db.get_user_by_verification_token(token)
            if not user:
                raise HTTPException(status_code=400, detail="Invalid or expired verification token")
            
            # Check if token is expired
            if user.verification_token_expires and user.verification_token_expires < datetime.now():
                raise HTTPException(status_code=400, detail="Verification token has expired")
            
            # Check if already verified
            if user.is_verified:
                return {
                    "message": "Email already verified",
                    "user_id": user.id,
                    "firstname": user.firstname,
                    "lastname": user.lastname,
                    "email": user.email,
                    "already_verified": True
                }
            
            # Mark user as verified
            self.db.verify_user_email(user.id)
            
            # Send welcome email
            from modules.auth.email_service import email_service
            email_service.send_verification_success_email(user.email, user.firstname)
            
            return {
                "message": "Email verified successfully! You can now log in.",
                "user_id": user.id,
                "email": user.email,
                "verified": True
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"DEBUG: Error in verify_email: {str(e)}")
            raise HTTPException(status_code=500, detail="Email verification error")
    
    def resend_verification_email(self, email: str) -> Dict[str, Any]:
        """Resend verification email to user"""
        try:
            # Find user by email
            user = self.db.get_user_by_email(email)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Check if already verified
            if user.is_verified:
                return {
                    "message": "Email is already verified",
                    "email": email,
                    "already_verified": True
                }
            
            # Send verification email
            from modules.auth.email_service import email_service
            email_sent = email_service.resend_verification_email(user.id, email, user.firstname)
            
            return {
                "message": "Verification email sent successfully" if email_sent else "Verification email could not be sent (check server configuration)",
                "email": email,
                "email_sent": email_sent
            }
            
        except HTTPException:
            raise
    def verify_email_otp(self, email: str, otp: str) -> Dict[str, Any]:
        """Verify user email using OTP code"""
        try:
            # Find user by email
            user = self.db.get_user_by_email(email)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Check if OTP matches
            if not user.verification_token or user.verification_token != otp:
                raise HTTPException(status_code=400, detail="Invalid verification code")
            
            # Check if OTP is expired
            if user.verification_token_expires and user.verification_token_expires < datetime.now():
                raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new one.")
            
            # Check if already verified
            if user.is_verified:
                return {
                    "message": "Email already verified",
                    "user_id": user.id,
                    "firstname": user.firstname,
                    "lastname": user.lastname,
                    "email": user.email,
                    "already_verified": True
                }
            
            # Mark user as verified
            self.db.verify_user_email(user.id)
            
            # Send welcome email
            from modules.auth.email_service import email_service
            email_service.send_verification_success_email(user.email, user.firstname)
            
            return {
                "message": "Email verified successfully! You can now log in.",
                "user_id": user.id,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "email": user.email,
                "verified": True
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"DEBUG: Error in verify_email_otp: {str(e)}")
            raise HTTPException(status_code=500, detail="Email verification error")
    
    def continue_with_google(self, id_token_str: str) -> Dict[str, Any]:
        """Google OAuth continue process - handles both signup and signin automatically"""
        print(f"DEBUG: Continue with Google called with token: {id_token_str[:50]}...")
        print(f"DEBUG: GOOGLE_CLIENT_ID configured: {bool(settings.GOOGLE_CLIENT_ID)}")
        
        if not settings.GOOGLE_CLIENT_ID:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
        # Validate that the token looks like a JWT (starts with 'eyJ')
        if not id_token_str.startswith('eyJ'):
            raise HTTPException(status_code=400, detail="Invalid ID token format. Expected JWT token starting with 'eyJ'")
        
        try:
            # Verify the Google ID token
            print(f"DEBUG: Attempting to verify token with client ID: {settings.GOOGLE_CLIENT_ID[:20]}...")
            idinfo = id_token.verify_oauth2_token(id_token_str, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
            print(f"DEBUG: Token verified successfully. User info: {idinfo.get('email', 'no_email')}")
            
            # Extract user information from Google
            google_user_id = idinfo['sub']
            email = idinfo['email']
            firstname = idinfo.get('given_name', '')
            lastname = idinfo.get('family_name', '')
            
            print(f"DEBUG: Extracted info - email: {email}, name: {firstname} {lastname}")
            
            # First, try to find user by Google ID
            existing_user = self.db.get_user_by_google_id(google_user_id)
            
            if existing_user:
                # User exists with this Google ID - sign them in
                print(f"DEBUG: User found by Google ID - signing in")
                return {
                    "message": "Welcome back! Signed in successfully",
                    "user_id": existing_user.id,
                    "firstname": existing_user.firstname,
                    "lastname": existing_user.lastname,
                    "email": existing_user.email,
                    "action": "signin"
                }
            
            # If not found by Google ID, try to find by email
            existing_user = self.db.get_user_by_email(email)
            
            if existing_user:
                # User exists with this email but no Google ID linked
                if existing_user.google_id is None:
                    # Link the Google ID to existing account and sign them in
                    print(f"DEBUG: User found by email, linking Google ID")
                    self.db.update_user_google_id(existing_user.id, google_user_id)
                    return {
                        "message": "Account linked successfully! Signed in with Google",
                        "user_id": existing_user.id,
                        "firstname": existing_user.firstname,
                        "lastname": existing_user.lastname,
                        "email": existing_user.email,
                        "action": "signin_and_link"
                    }
                else:
                    # User has different Google ID - this shouldn't happen but handle it
                    print(f"DEBUG: User has different Google ID linked")
                    raise HTTPException(
                        status_code=400, 
                        detail="This email is already associated with a different Google account"
                    )
            
            # User doesn't exist - create new account (signup)
            print(f"DEBUG: User not found - creating new account")
            
            # Generate a random password since they're using Google OAuth
            random_password = secrets.token_urlsafe(32)
            
            user_id = self.db.create_user(firstname, lastname, email, random_password, google_user_id)
            
            # Mark Google OAuth users as verified by default
            self.db.verify_user_email(user_id)
            
            return {
                "message": "Welcome! Account created successfully",
                "user_id": user_id,
                "firstname": firstname,
                "lastname": lastname,
                "email": email,
                "verified": True,
                "action": "signup"
            }
            
        except ValueError as e:
            # Invalid token
            print(f"DEBUG: Token validation failed: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid Google ID token: {str(e)}")
        except Exception as e:
            print(f"DEBUG: General error in continue_with_google: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Google authentication error: {str(e)}")

# Global auth service instance
auth_service = AuthService()