"""
Storage API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from modules.storage.service import storage_service
from modules.auth.deps import get_current_user_id

router = APIRouter(prefix="/storage", tags=["storage"])

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_id: str = Form(None),
    user_id: int = Depends(get_current_user_id)
):
    """Upload file with storage validation"""
    return storage_service.upload_file(user_id, file, project_id)

@router.delete("/file")
async def delete_file(
    file_url: str = Form(...),
    user_id: int = Depends(get_current_user_id)
):
    """Delete file and free up storage"""
    return storage_service.delete_file(user_id, file_url)

@router.get("/usage")
async def get_storage_usage(user_id: int = Depends(get_current_user_id)):
    """Get user storage usage information"""
    return storage_service.get_user_storage_info(user_id)