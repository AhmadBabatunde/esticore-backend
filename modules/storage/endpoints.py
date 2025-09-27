"""
Storage API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from modules.storage.service import storage_service
from modules.auth.service import auth_service

router = APIRouter(prefix="/storage", tags=["storage"])
security = HTTPBearer()

def verify_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to verify user JWT token"""
    token = credentials.credentials
    user_id = auth_service.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_id: str = Form(None),
    user_id: int = Depends(verify_user_token)
):
    """Upload file with storage validation"""
    return storage_service.upload_file(user_id, file, project_id)

@router.delete("/file")
async def delete_file(
    file_url: str = Form(...),
    user_id: int = Depends(verify_user_token)
):
    """Delete file and free up storage"""
    return storage_service.delete_file(user_id, file_url)

@router.get("/usage")
async def get_storage_usage(user_id: int = Depends(verify_user_token)):
    """Get user storage usage information"""
    return storage_service.get_user_storage_info(user_id)