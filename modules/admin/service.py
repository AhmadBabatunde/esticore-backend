"""
Admin services for the Floor Plan Agent API
"""
import hashlib
import jwt
import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import HTTPException

from modules.config.settings import settings
from modules.database import db_manager
from modules.admin.models import UserStatus, FeedbackType, SubscriptionInterval

class AdminService:
    """Admin service class"""
    
    def __init__(self):
        self.db = db_manager
        self.jwt_secret = settings.JWT_SECRET_KEY
        self.token_expiry = timedelta(hours=24)
    
    def admin_login(self, email: str, password: str) -> Dict[str, Any]:
        """Admin login process"""
        admin = self.db.verify_admin_credentials(email, password)
        if not admin:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
        
        # Update last login
        self.db.update_admin_last_login(admin.id)
        
        # Generate JWT token
        token = self.generate_admin_token(admin.id, admin.email, admin.is_super_admin)
        
        return {
            "message": "Admin login successful",
            "admin_id": admin.id,
            "username": admin.username,
            "email": admin.email,
            "is_super_admin": admin.is_super_admin,
            "token": token,
            "token_type": "bearer"
        }
    
    def admin_register(self, username: str, email: str, password: str, confirm_password: str, is_super_admin: bool) -> Dict[str, Any]:
        """Admin registration process"""
        # Check if super admin exists (only super admin can create other admins)
        super_admins = self.db.get_super_admins()
        if not super_admins and not is_super_admin:
            raise HTTPException(status_code=403, detail="First admin must be a super admin")
        
        if password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
        # Check if email already exists
        existing_admin = self.db.get_admin_by_email(email)
        if existing_admin:
            raise HTTPException(status_code=400, detail="Admin email already exists")
        
        try:
            admin_id = self.db.create_admin_user(username, email, password, is_super_admin)
            return {
                "message": "Admin created successfully",
                "admin_id": admin_id,
                "username": username,
                "email": email,
                "is_super_admin": is_super_admin
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    def generate_admin_token(self, admin_id: int, email: str, is_super_admin: bool) -> str:
        """Generate JWT token for admin"""
        payload = {
            "admin_id": admin_id,
            "email": email,
            "is_super_admin": is_super_admin,
            "exp": datetime.utcnow() + self.token_expiry
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def verify_admin_token(self, token: str) -> bool:
        """Verify admin JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return bool(payload.get("admin_id"))
        except jwt.ExpiredSignatureError:
            return False
        except jwt.InvalidTokenError:
            return False
    
    def get_all_users(self, page: int, limit: int, status: Optional[UserStatus], search: Optional[str]) -> Dict[str, Any]:
        """Get all users with pagination and filtering"""
        try:
            users = self.db.get_all_users_paginated(page, limit, status, search)
            total_users = self.db.get_total_users_count(status, search)
            
            return {
                "users": users,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_users,
                    "pages": (total_users + limit - 1) // limit
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")
    
    def delete_user(self, user_id: int) -> Dict[str, Any]:
        """Delete a user and all their data"""
        try:
            # Get user data before deletion for AWS cleanup
            user = self.db.get_user_by_id(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Delete user files from AWS (implement this in storage service)
            from modules.storage.service import storage_service
            storage_service.delete_user_files(user_id)
            
            # Delete user from database
            success = self.db.delete_user(user_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete user")
            
            return {
                "message": "User deleted successfully",
                "user_id": user_id,
                "email": user.email
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")
    
    def update_user_status(self, user_id: int, is_active: bool) -> Dict[str, Any]:
        """Update user active status"""
        try:
            success = self.db.update_user_status(user_id, is_active)
            if not success:
                raise HTTPException(status_code=404, detail="User not found")
            
            status = "active" if is_active else "inactive"
            return {
                "message": f"User status updated to {status}",
                "user_id": user_id,
                "is_active": is_active
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error updating user status: {str(e)}")
    
    def get_user_storage_stats(self, user_id: int) -> Dict[str, Any]:
        """Get user storage usage statistics"""
        try:
            user_storage = self.db.get_user_storage(user_id)
            user_subscription = self.db.get_user_subscription(user_id)
            
            if not user_storage or not user_subscription:
                raise HTTPException(status_code=404, detail="User storage or subscription not found")
            
            storage_limit_mb = user_subscription.plan.storage_gb * 1024
            used_percentage = (user_storage.used_storage_mb / storage_limit_mb) * 100
            
            return {
                "user_id": user_id,
                "used_storage_mb": user_storage.used_storage_mb,
                "storage_limit_mb": storage_limit_mb,
                "available_storage_mb": storage_limit_mb - user_storage.used_storage_mb,
                "used_percentage": round(used_percentage, 2),
                "last_updated": user_storage.last_updated
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching storage stats: {str(e)}")
    
    def update_user_storage(self, user_id: int, file_size_mb: float) -> Dict[str, Any]:
        """Update user storage usage"""
        try:
            # Check if user has sufficient storage
            user_storage = self.db.get_user_storage(user_id)
            user_subscription = self.db.get_user_subscription(user_id)
            
            if not user_subscription:
                raise HTTPException(status_code=400, detail="User has no active subscription")
            
            storage_limit_mb = user_subscription.plan.storage_gb * 1024
            new_usage = user_storage.used_storage_mb + file_size_mb
            
            if new_usage > storage_limit_mb:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Storage limit exceeded. Available: {storage_limit_mb - user_storage.used_storage_mb}MB, Required: {file_size_mb}MB"
                )
            
            # Update storage
            success = self.db.update_user_storage(user_id, new_usage)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update storage")
            
            return {
                "message": "Storage updated successfully",
                "user_id": user_id,
                "new_usage_mb": new_usage,
                "available_mb": storage_limit_mb - new_usage
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error updating storage: {str(e)}")
    
    def get_all_subscription_plans(self) -> Dict[str, Any]:
        """Get all subscription plans"""
        try:
            plans = self.db.get_all_subscription_plans()
            return {
                "plans": plans,
                "count": len(plans)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching subscription plans: {str(e)}")
    
    def create_subscription_plan(self, name: str, description: str, price_monthly: float, 
                               price_annual: float, storage_gb: int, project_limit: int,
                               user_limit: int, action_limit: int, features: List[str],
                               has_free_trial: bool, trial_days: int) -> Dict[str, Any]:
        """Create a new subscription plan"""
        try:
            plan_id = self.db.create_subscription_plan(
                name, description, price_monthly, price_annual, storage_gb,
                project_limit, user_limit, action_limit, features,
                has_free_trial, trial_days
            )
            
            return {
                "message": "Subscription plan created successfully",
                "plan_id": plan_id,
                "name": name
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating subscription plan: {str(e)}")
    
    def get_feedback_statistics(self) -> Dict[str, Any]:
        """Get feedback statistics"""
        try:
            stats = self.db.get_feedback_statistics()
            total = stats.get('total', 0)
            positive = stats.get('positive', 0)
            negative = stats.get('negative', 0)
            
            positive_percentage = (positive / total * 100) if total > 0 else 0
            negative_percentage = (negative / total * 100) if total > 0 else 0
            
            return {
                "total_feedback": total,
                "positive": positive,
                "negative": negative,
                "positive_percentage": round(positive_percentage, 2),
                "negative_percentage": round(negative_percentage, 2)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching feedback statistics: {str(e)}")
    
    def get_dashboard_statistics(self) -> Dict[str, Any]:
        """Get admin dashboard statistics"""
        try:
            total_users = self.db.get_total_users_count()
            active_users = self.db.get_active_users_count()
            total_feedback = self.db.get_total_feedback_count()
            recent_signups = self.db.get_recent_signups(7)  # Last 7 days
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": total_users - active_users,
                "total_feedback": total_feedback,
                "recent_signups": recent_signups,
                "storage_usage": self.db.get_total_storage_usage()
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching dashboard statistics: {str(e)}")
    
    def get_subscription_reminders(self) -> Dict[str, Any]:
        """Get users who need subscription reminders"""
        try:
            # Users with subscriptions expiring in 30 days
            expiring_soon = self.db.get_subscriptions_expiring_soon(30)
            
            # Users with expired subscriptions (less than 21 days ago)
            recently_expired = self.db.get_recently_expired_subscriptions(21)
            
            return {
                "expiring_soon": expiring_soon,
                "recently_expired": recently_expired
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching subscription reminders: {str(e)}")

# Global admin service instance
admin_service = AdminService()