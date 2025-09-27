"""
Background tasks for subscription reminders and cleanup
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from modules.database import db_manager
from modules.config.settings import settings

class SubscriptionTasks:
    """Background tasks for subscription management"""
    
    def __init__(self):
        self.db = db_manager
    
    async def send_subscription_reminders(self):
        """Send subscription expiration reminders"""
        try:
            # Get subscriptions expiring in 30 days
            expiring_soon = self.db.get_subscriptions_expiring_soon(30)
            
            for subscription in expiring_soon:
                await self._send_reminder_email(
                    subscription['user_email'],
                    subscription['plan_name'],
                    subscription['expiry_date'],
                    "30 days"
                )
            
            # Get subscriptions that expired recently (send follow-up)
            recently_expired = self.db.get_recently_expired_subscriptions(21)
            
            for subscription in recently_expired:
                days_expired = (datetime.now() - subscription['expiry_date']).days
                await self._send_expiry_followup(
                    subscription['user_email'],
                    subscription['plan_name'],
                    days_expired
                )
            
            print(f"Sent reminders to {len(expiring_soon)} users and follow-ups to {len(recently_expired)} users")
            
        except Exception as e:
            print(f"Error sending reminders: {str(e)}")
    
    async def cleanup_expired_subscriptions(self):
        """Clean up expired subscriptions and user data"""
        try:
            # Get subscriptions expired more than 30 days ago
            long_expired = self.db.get_recently_expired_subscriptions(30)
            
            for subscription in long_expired:
                # Delete user files from AWS
                from modules.storage.service import storage_service
                storage_service.delete_user_files(subscription['user_id'])
                
                # Deactivate subscription
                self.db.update_user_subscription(
                    subscription['subscription_id'],
                    is_active=False,
                    status='expired'
                )
                
                print(f"Cleaned up expired subscription for user {subscription['user_email']}")
            
        except Exception as e:
            print(f"Error cleaning up subscriptions: {str(e)}")
    
    async def _send_reminder_email(self, email: str, plan_name: str, expiry_date: datetime, days: str):
        """Send subscription reminder email"""
        try:
            if not settings.SMTP_HOST:
                return  # Email not configured
            
            message = MIMEMultipart()
            message['From'] = settings.SMTP_USERNAME
            message['To'] = email
            message['Subject'] = f"Your {plan_name} Subscription Expires in {days}"
            
            body = f"""
            Hello,
            
            This is a friendly reminder that your {plan_name} subscription will expire on {expiry_date.strftime('%Y-%m-%d')}.
            
            To avoid interruption of service, please renew your subscription before the expiration date.
            
            Best regards,
            The EstiCore Team
            """
            
            message.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(message)
            
            print(f"Sent reminder email to {email}")
            
        except Exception as e:
            print(f"Error sending email to {email}: {str(e)}")
    
    async def run_scheduled_tasks(self):
        """Run all scheduled tasks"""
        while True:
            try:
                # Run daily at 2 AM
                now = datetime.now()
                if now.hour == 2 and now.minute < 5:  # Run once between 2:00-2:05 AM
                    await self.send_subscription_reminders()
                    await self.cleanup_expired_subscriptions()
                    await asyncio.sleep(300)  # Sleep 5 minutes to avoid multiple runs
                else:
                    await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                print(f"Error in scheduled tasks: {str(e)}")
                await asyncio.sleep(60)

# Global tasks instance
subscription_tasks = SubscriptionTasks()