"""
Profile API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, HTTPException, Depends, Form, UploadFile, File
from modules.profile.service import profile_service
from modules.auth.deps import get_current_user_id

router = APIRouter(prefix="/profile", tags=["profile"])

@router.get("/")
async def get_profile(user_id: int = Depends(get_current_user_id)):
    """Get user profile"""
    return profile_service.get_user_profile(user_id)

@router.put("/")
async def update_profile(
    firstname: str = Form(None),
    lastname: str = Form(None),
    user_id: int = Depends(get_current_user_id)
):
    """Update user profile"""
    return profile_service.update_profile(user_id, firstname, lastname)

@router.post("/image")
async def upload_profile_image(
    image: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id)
):
    """Upload profile image"""
    return profile_service.upload_profile_image(user_id, image)

@router.delete("/image")
async def delete_profile_image(user_id: int = Depends(get_current_user_id)):
    """Delete profile image"""
    return profile_service.delete_profile_image(user_id)

@router.get("/recent-projects")
async def get_recently_viewed_projects(user_id: int = Depends(get_current_user_id)):
    """Get user's recently viewed projects"""
    return profile_service.get_recently_viewed_projects(user_id)
