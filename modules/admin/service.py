"""
Admin services for the Floor Plan Agent API
"""
import hashlib
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
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
        self.token_expiry = timedelta(hours=24*7 )
    
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
        # super_admins = self.db.get_super_admins()
        # if not super_admins and not is_super_admin:
        #     raise HTTPException(status_code=403, detail="First admin must be a super admin")
        
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
        except ExpiredSignatureError:
            return False
        except InvalidTokenError:
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
            print(f"Error fetching storage stats: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching storage stats:")
    
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

            sth = self.db.debug_plan_features(8)
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

    def update_subscription_plan(self, plan_id: int, name: Optional[str] = None,
                           description: Optional[str] = None, price_monthly: Optional[float] = None,
                           price_annual: Optional[float] = None, storage_gb: Optional[int] = None,
                           project_limit: Optional[int] = None, user_limit: Optional[int] = None,
                           action_limit: Optional[int] = None, features: Optional[List[str]] = None,
                           is_active: Optional[bool] = None) -> Dict[str, Any]:
        """Update a subscription plan with partial data"""
        try:
            # Check if plan exists before update
            existing_plan = self.db.get_subscription_plan_by_id(plan_id)
            if not existing_plan:
                raise HTTPException(status_code=404, detail="Subscription plan not found")

            # Prepare update data from provided fields
            update_data = {}
            if name is not None:
                update_data['name'] = name
            if description is not None:
                update_data['description'] = description
            if price_monthly is not None:
                update_data['price_monthly'] = price_monthly
            if price_annual is not None:
                update_data['price_annual'] = price_annual
            if storage_gb is not None:
                update_data['storage_gb'] = storage_gb
            if project_limit is not None:
                update_data['project_limit'] = project_limit
            if user_limit is not None:
                update_data['user_limit'] = user_limit
            if action_limit is not None:
                update_data['action_limit'] = action_limit
            if features is not None:
                update_data['features'] = features  # This will be JSON encoded in the DB manager
            if is_active is not None:
                update_data['is_active'] = is_active

            # Perform the update
            success = self.db.update_subscription_plan(plan_id, **update_data)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update subscription plan")

            # Fetch and return the updated plan
            updated_plan = self.db.get_subscription_plan_by_id(plan_id)
            return {
                "message": "Subscription plan updated successfully",
                "plan_id": plan_id,
                "plan": updated_plan
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error updating subscription plan: {str(e)}")

    def delete_subscription_plan(self, plan_id: int) -> Dict[str, Any]:
        """Delete a subscription plan"""
        try:
            # First, check if the plan exists
            plan = self.db.get_subscription_plan_by_id(plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Subscription plan not found")
            
            # Check if any users are currently subscribed to this plan
            # You might want to add this method to your DatabaseManager
            # active_subscriptions = self.db.get_active_subscriptions_count_by_plan(plan_id)
            # if active_subscriptions > 0:
            #     raise HTTPException(
            #         status_code=400, 
            #         detail=f"Cannot delete plan with {active_subscriptions} active subscriptions"
            #     )
            
            # Delete the plan from database
            success = self.db.delete_subscription_plan(plan_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete subscription plan")
            
            return {
                "message": "Subscription plan deleted successfully",
                "plan_id": plan_id,
                "plan_name": plan.name
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error deleting subscription plan: {str(e)}")        
        
    def get_all_feedback(self, page: int = 1, limit: int = 20, rating: Optional[str] = None) -> Dict[str, Any]:
        """Get all feedback with pagination and filtering"""
        try:
            # Validate input parameters
            if page < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Page must be greater than 0"
                )
            
            if limit < 1 or limit > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Limit must be between 1 and 100"
                )
            
            # Validate rating if provided
            if rating and rating not in ['positive', 'negative']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Rating must be either 'positive' or 'negative'"
                )
            
            # Get feedback from database
            feedback_list = self.db.get_all_feedback(page, limit, rating)
            
            # Calculate pagination metadata
            total_feedback = self.db.get_total_feedback_count(rating)
            total_pages = (total_feedback + limit - 1) // limit if total_feedback > 0 else 1
            
            return {
                "feedback": feedback_list,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_feedback,
                    "pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Log the error for debugging
            print(f"Error in get_all_feedback service: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Unable to fetch feedback data"
            )
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
            # recent_signups = self.db.get_recent_signups(7)  # Last 7 days
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": total_users - active_users,
                "total_feedback": total_feedback,
                # "recent_signups": recent_signups,
                "storage_usage": self.db.get_total_storage_usage()
            }
        except Exception as e:
            # raise HTTPException(status_code=500, detail=f"Error fetching dashboard statistics: {str(e)}")
                    # Log the actual error for debugging
            print(f"Database error in get_dashboard_statistics: {str(e)}")
            # Return generic error to client
            raise HTTPException(
                status_code=500,
                detail="Unable to fetch dashboard statistics"
            )
    
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
            raise HTT
            


    # Add these methods to your AdminService class
    def get_ai_models(self) -> Dict[str, Any]:
        """Get all AI models"""
        try:
            models = self.db.get_all_ai_models()
            return {
                "models": models,
                "count": len(models)
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching AI models: {str(e)}"
            )

    def create_ai_model(self, name: str, provider: str, model_name: str, 
                    config: Dict[str, Any], is_active: bool = False) -> Dict[str, Any]:
        """Create a new AI model configuration"""
        try:
            # Validate that config is a dictionary
            if not isinstance(config, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Config must be a valid JSON object"
                )
            
            # If activating this model, deactivate others first
            if is_active:
                active_model = self.db.get_active_ai_model()
                if active_model:
                    self.db.activate_ai_model(0)  # Deactivate all first
            
            model_id = self.db.create_ai_model(name, provider, model_name, config, is_active)
            
            return {
                "message": "AI model created successfully",
                "model_id": model_id,
                "name": name,
                "provider": provider,
                "is_active": is_active
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating AI model: {str(e)}"
            )

    def activate_ai_model(self, model_id: int) -> Dict[str, Any]:
        """Activate an AI model"""
        try:
            # First check if model exists
            all_models = self.db.get_all_ai_models()
            model_exists = any(model.id == model_id for model in all_models)
            
            if not model_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"AI model with ID {model_id} not found"
                )
            
            success = self.db.activate_ai_model(model_id)
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to activate AI model"
                )
            
            return {
                "message": "AI model activated successfully",
                "model_id": model_id,
                "active": True
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error activating AI model: {str(e)}"
            )

    def get_active_ai_model(self) -> Dict[str, Any]:
        """Get the currently active AI model"""
        try:
            active_model = self.db.get_active_ai_model()
            
            if not active_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active AI model found"
                )
            
            return {
                "active_model": active_model,
                "message": "Active AI model retrieved successfully"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error fetching active AI model: {str(e)}"
            )

    def delete_ai_model(self, model_id: int) -> Dict[str, Any]:
        """Delete an AI model configuration"""
        try:
            # First check if this is the active model
            active_model = self.db.get_active_ai_model()
            if active_model and active_model.id == model_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the active AI model. Activate another model first."
                )
            
            success = self.db.delete_ai_model(model_id)
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"AI model with ID {model_id} not found"
                )
            
            return {
                "message": "AI model deleted successfully",
                "model_id": model_id,
                "deleted": True
            }
        except HTTPException:
            raise
        except Exception as e:
            if "Cannot delete the active AI model" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting AI model: {str(e)}"
            )
# Global admin service instance
admin_service = AdminService()

