"""
General API endpoints for the Floor Plan Agent API
"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from modules.config.settings import settings
from modules.config.utils import validate_file_path

router = APIRouter(tags=["general"])

@router.get("/")
def root():
    """API root endpoint"""
    return {
        "message": f"{settings.APP_NAME} is running",
        "version": settings.VERSION,
        "status": "healthy"
    }

@router.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.VERSION
    }

@router.get("/download")
async def download_file(path: str):
    """
    Download files with security validation
    Only allows downloads from the DATA_DIR for security
    """
    # Security: strictly allow only within DATA_DIR
    if not validate_file_path(path, settings.DATA_DIR):
        raise HTTPException(404, detail="File not found")
    
    filename = os.path.basename(path)
    return FileResponse(path, filename=filename)