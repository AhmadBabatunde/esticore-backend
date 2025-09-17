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
    print(f"DEBUG: Download request for path: {path}")
    print(f"DEBUG: Current DATA_DIR: {settings.DATA_DIR}")
    print(f"DEBUG: Path exists: {os.path.exists(path)}")
    
    # First, try the path as-is within DATA_DIR
    if validate_file_path(path, settings.DATA_DIR):
        filename = os.path.basename(path)
        print(f"DEBUG: Returning file using original path: {path}")
        return FileResponse(path, filename=filename)
    
    # If that fails, try common deployment path corrections
    # This handles cases where paths were stored with different working directories
    potential_paths = []
    
    # If the path looks like it's already absolute, try to find it relative to our dirs
    if os.path.isabs(path):
        filename_only = os.path.basename(path)
        potential_paths.extend([
            os.path.join(settings.DOCS_DIR, filename_only),
            os.path.join(settings.OUTPUT_DIR, filename_only),
            os.path.join(settings.IMAGES_DIR, filename_only),
        ])
    
    # Try each potential path
    for potential_path in potential_paths:
        print(f"DEBUG: Trying potential path: {potential_path}")
        if validate_file_path(potential_path, settings.DATA_DIR):
            filename = os.path.basename(potential_path)
            print(f"DEBUG: Found file at corrected path: {potential_path}")
            return FileResponse(potential_path, filename=filename)
    
    print(f"DEBUG: File not found in any location")
    raise HTTPException(404, detail="File not found")

@router.post("/download/pdf")
async def download_pdf(user_id: int, doc_id: str):
    """
    Download a PDF document for a specific user and document ID
    """
    print(f"DEBUG: PDF download request for doc_id: {doc_id}, user_id: {user_id}")
    
    # Get document information
    try:
        doc_info = pdf_processor.get_document_info(doc_id)
        print(f"DEBUG: Document info retrieved: {doc_info}")
    except FileNotFoundError:
        print(f"DEBUG: Document {doc_id} not found in database")
        raise HTTPException(404, detail="Document not found")

    if not doc_info:
        raise HTTPException(404, detail="Document not found")

    pdf_path = doc_info["pdf_path"]
    print(f"DEBUG: Document pdf_path: {pdf_path}")
    print(f"DEBUG: File exists at pdf_path: {os.path.exists(pdf_path)}")
    print(f"DEBUG: Current DOCS_DIR: {settings.DOCS_DIR}")
    
    # First, try the stored path as-is
    if validate_file_path(pdf_path, settings.DOCS_DIR):
        filename = os.path.basename(pdf_path)
        print(f"DEBUG: Returning PDF using stored path: {pdf_path}")
        return FileResponse(pdf_path, filename=filename)
    
    # If that fails, try to find the file by doc_id in our docs directory
    # This handles cases where the stored path is incorrect due to deployment path changes
    potential_pdf_paths = [
        os.path.join(settings.DOCS_DIR, f"{doc_id}.pdf"),
        os.path.join(settings.OUTPUT_DIR, f"{doc_id}.pdf"),
    ]
    
    # Also try looking for files that start with the doc_id (for annotation outputs)
    if os.path.exists(settings.OUTPUT_DIR):
        for filename in os.listdir(settings.OUTPUT_DIR):
            if filename.startswith(doc_id) and filename.endswith('.pdf'):
                potential_pdf_paths.append(os.path.join(settings.OUTPUT_DIR, filename))
    
    if os.path.exists(settings.DOCS_DIR):
        for filename in os.listdir(settings.DOCS_DIR):
            if filename.startswith(doc_id) and filename.endswith('.pdf'):
                potential_pdf_paths.append(os.path.join(settings.DOCS_DIR, filename))
    
    # Try each potential path
    for potential_path in potential_pdf_paths:
        print(f"DEBUG: Trying potential PDF path: {potential_path}")
        if os.path.exists(potential_path) and validate_file_path(potential_path, settings.DATA_DIR):
            filename = os.path.basename(potential_path)
            print(f"DEBUG: Found PDF at corrected path: {potential_path}")
            return FileResponse(potential_path, filename=filename)
    
    print(f"DEBUG: PDF file not found in any location for doc_id: {doc_id}")
    raise HTTPException(404, detail="PDF file not found")
