"""Feedback API endpoints for the Floor Plan Agent API."""

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from modules.admin.models import FeedbackType
from modules.auth.service import auth_service
from modules.feedback.service import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])
security = HTTPBearer()

def verify_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to verify user JWT token"""
    token = credentials.credentials
    user_id = auth_service.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

@router.post("/submit")
async def submit_feedback(
    ai_response: str = Form(...),
    rating: FeedbackType = Form(...),
    project_name: Optional[str] = Form(None),
    user_id: int = Depends(verify_user_token)
):
    """Submit user feedback for AI responses"""
    # Get user email for feedback
    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return feedback_service.submit_feedback(
        user_id, user.email, ai_response, rating, project_name
    )

@router.get("/user")
async def get_user_feedback(
    page: int = 1,
    limit: int = 20,
    user_id: int = Depends(verify_user_token)
):
    """Get user's feedback history"""
    return feedback_service.get_user_feedback(user_id, page, limit)

@router.get("/stats")
async def get_feedback_stats():
    """Get feedback statistics (public endpoint)"""
    return feedback_service.get_feedback_statistics()