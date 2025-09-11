"""
Authentication services for the Floor Plan Agent API
"""
import secrets
from typing import Optional, Dict, Any
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
            return {
                "message": "User created successfully",
                "user_id": user_id,
                "firstname": firstname,
                "lastname": lastname,
                "email": email
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    def login_user(self, email: str, password: str) -> Dict[str, Any]:
        """Regular login process"""
        # Validate email format
        if not self.validate_email_format(email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Verify credentials
        user = self.db.verify_user_credentials(email, password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return {
            "message": "Login successful",
            "user_id": user.id,
            "firstname": user.firstname,
            "lastname": user.lastname,
            "email": user.email
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
            
            return {
                "message": "User created successfully",
                "user_id": user_id,
                "firstname": firstname,
                "lastname": lastname,
                "email": email
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

# Global auth service instance
auth_service = AuthService()