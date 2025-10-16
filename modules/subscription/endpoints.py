"""
Subscription API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, HTTPException, Depends, Form, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import stripe

from modules.subscription.service import Subscription_Service  
from modules.auth.service import auth_service
from modules.config.settings import settings

router = APIRouter(prefix="/subscription", tags=["subscription"])
security = HTTPBearer()

def verify_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to verify user JWT token"""
    token = credentials.credentials
    user_id = auth_service.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

@router.get("/plans")
async def get_subscription_plans():
    """Get all available subscription plans"""
    print("route hit")
    return Subscription_Service.get_available_plans()

@router.get("/user")
async def get_user_subscription(user_id: int = Depends(verify_user_token)):
    """Get user's current subscription"""
    return Subscription_Service.get_user_subscription(user_id)

@router.post("/create-checkout-session")
async def create_checkout_session(
    plan_id: int = Form(...),
    interval: str = Form(...),  # 'monthly' or 'annual'
    user_id: int = Depends(verify_user_token)
):
    """Create Stripe checkout session"""
    return Subscription_Service.create_checkout_session(user_id, plan_id, interval)

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        return Subscription_Service.handle_stripe_webhook(payload, sig_header)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cancel")
async def cancel_subscription(user_id: int = Depends(verify_user_token)):
    """Cancel user subscription"""
    return Subscription_Service.cancel_subscription(user_id)

@router.post("/reactivate")
async def reactivate_subscription(user_id: int = Depends(verify_user_token)):
    """Reactivate user subscription"""
    return Subscription_Service.reactivate_subscription(user_id)

@router.get("/invoices")
async def get_invoices(user_id: int = Depends(verify_user_token), limit: int = 10):
    """Get user's payment invoices"""
    return Subscription_Service.get_user_invoices(user_id, limit)