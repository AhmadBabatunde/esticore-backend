"""
Subscription services for the Floor Plan Agent API
"""
import stripe
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from modules.config.settings import settings
from modules.database import db_manager
from modules.subscription.models import SubscriptionInterval

class SubscriptionService:
    """Subscription service class"""
    
    def __init__(self):
        self.db = db_manager
        self.stripe_api_key = settings.STRIPE_SECRET_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        
        # Configure Stripe
        if self.stripe_api_key:
            stripe.api_key = self.stripe_api_key
    
    def get_available_plans(self) -> Dict[str, Any]:
        """Get all available subscription plans"""
        try:
            plans = self.db.get_all_subscription_plans()
            active_plans = [plan for plan in plans if plan.is_active]
            
            return {
                "plans": active_plans,
                "count": len(active_plans)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching plans: {str(e)}")
    
    def get_user_subscription(self, user_id: int) -> Dict[str, Any]:
        """Get user's current subscription"""
        try:
            subscription = self.db.get_user_subscription(user_id)
            user_storage = self.db.get_user_storage(user_id)
            
            if not subscription:
                # Check if user has a free trial
                user = self.db.get_user_by_id(user_id)
                if user and (datetime.now() - user.created_at).days <= 30:
                    # User is within trial period
                    trial_plan = self._get_trial_plan()
                    return {
                        "has_subscription": False,
                        "on_trial": True,
                        "trial_days_left": 30 - (datetime.now() - user.created_at).days,
                        "trial_plan": trial_plan,
                        "storage_usage": user_storage.used_storage_mb if user_storage else 0
                    }
                
                return {
                    "has_subscription": False,
                    "on_trial": False,
                    "storage_usage": user_storage.used_storage_mb if user_storage else 0
                }
            
            plan = self.db.get_subscription_plan_by_id(subscription.plan_id)
            
            return {
                "has_subscription": True,
                "subscription": subscription,
                "plan": plan,
                "storage_usage": user_storage.used_storage_mb if user_storage else 0,
                "storage_limit_mb": plan.storage_gb * 1024 if plan else 0,
                "days_until_expiry": (subscription.current_period_end - datetime.now()).days if subscription.current_period_end else 0
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching subscription: {str(e)}")
    
    def create_checkout_session(self, user_id: int, plan_id: int, interval: str) -> Dict[str, Any]:
        """Create Stripe checkout session"""
        if not self.stripe_api_key:
            raise HTTPException(status_code=500, detail="Stripe not configured")
        
        try:
            # Get user and plan details
            user = self.db.get_user_by_id(user_id)
            plan = self.db.get_subscription_plan_by_id(plan_id)
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")
            
            # Determine price based on interval
            if interval == SubscriptionInterval.ANNUAL:
                price_amount = int(plan.price_annual * 100)  # Convert to cents
                interval_display = "year"
            else:
                price_amount = int(plan.price_monthly * 100)
                interval_display = "month"
            
            # Create Stripe checkout session
            checkout_session = stripe.checkout.Session.create(
                customer_email=user.email,
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': plan.name,
                            'description': plan.description,
                        },
                        'unit_amount': price_amount,
                        'recurring': {
                            'interval': interval,
                        },
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f"{settings.FRONTEND_URL}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.FRONTEND_URL}/subscription/cancel",
                metadata={
                    'user_id': str(user_id),
                    'plan_id': str(plan_id),
                    'interval': interval
                }
            )
            
            return {
                "checkout_url": checkout_session.url,
                "session_id": checkout_session.id,
                "message": f"Checkout session created for {plan.name} ({interval_display})"
            }
        except stripe.error.StripeError as e:
            raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error creating checkout session: {str(e)}")
    
    def handle_stripe_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Handle Stripe webhook events"""
        if not self.webhook_secret:
            raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")
        
        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )
            
            # Handle different event types
            if event['type'] == 'checkout.session.completed':
                return self._handle_checkout_session_completed(event)
            elif event['type'] == 'customer.subscription.updated':
                return self._handle_subscription_updated(event)
            elif event['type'] == 'customer.subscription.deleted':
                return self._handle_subscription_deleted(event)
            elif event['type'] == 'invoice.payment_succeeded':
                return self._handle_invoice_payment_succeeded(event)
            elif event['type'] == 'invoice.payment_failed':
                return self._handle_invoice_payment_failed(event)
            else:
                return {"status": "ignored", "event_type": event['type']}
                
        except stripe.error.SignatureVerificationError as e:
            raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Webhook error: {str(e)}")
    
    def _handle_checkout_session_completed(self, event) -> Dict[str, Any]:
        """Handle checkout.session.completed event"""
        session = event['data']['object']
        user_id = int(session['metadata']['user_id'])
        plan_id = int(session['metadata']['plan_id'])
        interval = session['metadata']['interval']
        
        # Create or update user subscription
        subscription = self.db.get_user_subscription(user_id)
        if subscription:
            # Update existing subscription
            self.db.update_user_subscription(
                subscription.id,
                plan_id=plan_id,
                stripe_subscription_id=session['subscription'],
                stripe_customer_id=session['customer'],
                interval=interval,
                status='active',
                is_active=True
            )
        else:
            # Create new subscription
            self.db.create_user_subscription(
                user_id, plan_id, session['subscription'], session['customer'], interval
            )
        
        # Ensure user has storage record
        if not self.db.get_user_storage(user_id):
            self.db.create_user_storage(user_id)
        
        return {"status": "success", "action": "subscription_created"}
    
    def _handle_subscription_updated(self, event) -> Dict[str, Any]:
        """Handle subscription updated event"""
        subscription = event['data']['object']
        
        # Update subscription in database
        db_subscription = self.db.get