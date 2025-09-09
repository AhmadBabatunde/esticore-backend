"""
General API endpoints for the Floor Plan Agent API
"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from modules.config.settings import settings
from modules.config.utils import validate_file_path
from modules.pdf_processing.service import pdf_processor  # Import pdf_processor

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

@router.post("/download/pdf")
async def download_pdf(user_id: int, doc_id: str):
    """
    Download a PDF document for a specific user and document ID
    """
    # Get document information
    try:
        doc_info = pdf_processor.get_document_info(doc_id)
    except FileNotFoundError:
        raise HTTPException(404, detail="Document not found")

    # Verify document exists in registry (already done by get_document_info)
    # For now, we'll skip user ownership check since it's not implemented in the system
    # In a real implementation, we would check if the user has access to this document
    # based on our access control system
    # Here we're just ensuring the document exists
    if not doc_info:
        raise HTTPException(404, detail="Document not found")

    # Security: ensure the file path is within the DOCS_DIR
    if not validate_file_path(doc_info["pdf_path"], settings.DOCS_DIR):
        raise HTTPException(404, detail="File not found")

    filename = os.path.basename(doc_info["pdf_path"])
    return FileResponse(doc_info["pdf_path"], filename=filename)
