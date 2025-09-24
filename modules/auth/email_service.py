"""
Email service for sending verification and notification emails
"""
import smtplib
import uuid
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from modules.config.settings import settings
from modules.database import db_manager

class EmailService:
    """Email service for sending verification emails"""
    
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL
        self.frontend_url = settings.FRONTEND_URL
    
    def is_configured(self) -> bool:
        """Check if email service is properly configured"""
        return bool(self.smtp_server and self.smtp_username and self.smtp_password)
    
    def generate_verification_token(self) -> str:
        """Generate a unique verification token"""
        return str(uuid.uuid4())
    
    def send_verification_email(self, user_id: int, email: str, firstname: str) -> bool:
        """Send email verification email to user"""
        if not self.is_configured():
            print("WARNING: Email service not configured - verification email not sent")
            return False
        
        try:
            # Generate verification token
            token = self.generate_verification_token()
            expires_at = datetime.now() + timedelta(hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS)
            
            # Store token in database
            db_manager.create_verification_token(user_id, token, expires_at)
            
            # Create verification URL
            verification_url = f"{self.frontend_url}/verify?token={token}"
            
            # Create email content
            subject = "Verify your email address - Esticore"
            
            # HTML email template
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Verification</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #666; }}
        .token {{ background: #f0f0f0; padding: 10px; border-radius: 5px; font-family: monospace; margin: 10px 0; word-break: break-all; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to Esticore!</h1>
            <p>Please verify your email address</p>
        </div>
        <div class="content">
            <h2>Hi {firstname}!</h2>
            <p>Thank you for signing up for Esticore. To complete your registration and start using our AI-powered floor plan analysis platform, please verify your email address.</p>
            
            <p><strong>Click the button below to verify your email:</strong></p>
            <p style="text-align: center;">
                <a href="{verification_url}" class="button">Verify Email Address</a>
            </p>
            
            <p>Or copy and paste this link into your browser:</p>
            <div class="token">{verification_url}</div>
            
            <p><strong>Important:</strong> This verification link will expire in {settings.VERIFICATION_TOKEN_EXPIRE_HOURS} hours.</p>
            
            <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
            
            <p><strong>What's next?</strong></p>
            <ul>
                <li>Upload your floor plan documents</li>
                <li>Use AI-powered analysis and annotation tools</li>
                <li>Manage your projects efficiently</li>
                <li>Access advanced document processing features</li>
            </ul>
            
            <p>If you didn't create this account, you can safely ignore this email.</p>
        </div>
        <div class="footer">
            <p>This email was sent by Esticore. If you have questions, please contact our support team.</p>
            <p>Token: {token[:8]}...</p>
        </div>
    </div>
</body>
</html>
            """
            
            # Plain text version (fallback)
            text_body = f"""
Hi {firstname}!

Welcome to Esticore! Please verify your email address to complete your registration.

Verification Link:
{verification_url}

This link will expire in {settings.VERIFICATION_TOKEN_EXPIRE_HOURS} hours.

What's next after verification:
- Upload your floor plan documents
- Use AI-powered analysis and annotation tools
- Manage your projects efficiently
- Access advanced document processing features

If you didn't create this account, you can safely ignore this email.

---
Esticore Team
Token: {token[:8]}...
            """
            
            # Send email
            return self._send_email(email, subject, text_body, html_body)
            
        except Exception as e:
            print(f"ERROR: Failed to send verification email: {e}")
            return False
    
    def send_verification_success_email(self, email: str, firstname: str) -> bool:
        """Send confirmation email after successful verification"""
        if not self.is_configured():
            return False
        
        try:
            subject = "Email Verified Successfully - Welcome to Esticore!"
            
            html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Verified</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
        .success {{ background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .button {{ display: inline-block; padding: 12px 30px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎉 Email Verified!</h1>
            <p>Your account is now active</p>
        </div>
        <div class="content">
            <div class="success">
                <strong>Success!</strong> Your email address has been verified successfully.
            </div>
            
            <h2>Hi {firstname}!</h2>
            <p>Congratulations! Your email has been verified and your Esticore account is now fully active.</p>
            
            <p style="text-align: center;">
                <a href="{self.frontend_url}/login" class="button">Start Using Esticore</a>
            </p>
            
            <p><strong>What you can do now:</strong></p>
            <ul>
                <li>Upload and process floor plan documents</li>
                <li>Use AI-powered annotation tools</li>
                <li>Create and manage projects</li>
                <li>Access all premium features</li>
            </ul>
            
            <p>Welcome aboard! We're excited to help you with your floor plan analysis needs.</p>
        </div>
    </div>
</body>
</html>
            """
            
            text_body = f"""
Hi {firstname}!

🎉 Your email has been verified successfully!

Your Esticore account is now fully active and ready to use.

What you can do now:
- Upload and process floor plan documents
- Use AI-powered annotation tools
- Create and manage projects
- Access all premium features

Welcome aboard! We're excited to help you with your floor plan analysis needs.

Login at: {self.frontend_url}/login

---
Esticore Team
            """
            
            return self._send_email(email, subject, text_body, html_body)
            
        except Exception as e:
            print(f"ERROR: Failed to send verification success email: {e}")
            return False
    
    def resend_verification_email(self, user_id: int, email: str, firstname: str) -> bool:
        """Resend verification email (generates new token)"""
        return self.send_verification_email(user_id, email, firstname)
    
    def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str = None) -> bool:
        """Send email using SMTP"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"Esticore <{self.from_email}>"
            msg['To'] = to_email
            
            # Attach parts
            part1 = MIMEText(text_body, 'plain')
            msg.attach(part1)
            
            if html_body:
                part2 = MIMEText(html_body, 'html')
                msg.attach(part2)
            
            # Connect and send
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            print(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            print(f"SMTP Error: Failed to send email to {to_email}: {e}")
            return False

# Global email service instance
email_service = EmailService()