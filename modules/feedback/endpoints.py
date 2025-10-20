"""Feedback API endpoints for the Floor Plan Agent API."""

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from modules.admin.models import FeedbackType
from modules.auth.deps import get_current_user_id
from modules.feedback.service import feedback_service

router = APIRouter(prefix="/feedback", tags=["feedback"])

@router.post("/submit")
async def submit_feedback(
    ai_response: str = Form(...),
    rating: FeedbackType = Form(...),
    project_name: Optional[str] = Form(None),
    user_id: int = Depends(get_current_user_id)
):
    """Submit user feedback for AI responses"""
    # Get user email for feedback
    from modules.auth.service import auth_service
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
    user_id: int = Depends(get_current_user_id)
):
    """Get user's feedback history"""
    return feedback_service.get_user_feedback(user_id, page, limit)

@router.get("/stats")
async def get_feedback_stats():
    """Get feedback statistics (public endpoint)"""
    return feedback_service.get_feedback_statistics()