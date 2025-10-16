"""
Profile API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, HTTPException, Depends, Form, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from modules.profile.service import profile_service
from modules.auth.service import auth_service

router = APIRouter(prefix="/profile", tags=["profile"])
security = HTTPBearer()

def verify_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to verify user JWT token"""
    token = credentials.credentials
    user_id = auth_service.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

@router.get("/")
async def get_profile(user_id: int = Depends(verify_user_token)):
    """Get user profile"""
    return profile_service.get_user_profile(user_id)

@router.put("/")
async def update_profile(
    firstname: str = Form(None),
    lastname: str = Form(None),
    user_id: int = Depends(verify_user_token)
):
    """Update user profile"""
    return profile_service.update_profile(user_id, firstname, lastname)

@router.post("/image")
async def upload_profile_image(
    image: UploadFile = File(...),
    user_id: int = Depends(verify_user_token)
):
    """Upload profile image"""
    return profile_service.upload_profile_image(user_id, image)

@router.delete("/image")
async def delete_profile_image(user_id: int = Depends(verify_user_token)):
    """Delete profile image"""
    return profile_service.delete_profile_image(user_id)

@router.get("/recent-projects")
async def get_recently_viewed_projects(user_id: int = Depends(verify_user_token)):
    """Get user's recently viewed projects"""
    return profile_service.get_recently_viewed_projects(user_id)