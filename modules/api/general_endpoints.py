"""
General API endpoints for the Floor Plan Agent API
"""
import os
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from modules.config.settings import settings
from modules.config.utils import validate_file_path
from modules.pdf_processing.service import pdf_processor  # Import pdf_processor
from modules.database.models import db_manager

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
            os.path.join(settings.DOCS_DIR, filename_only) if settings.DOCS_DIR else None,
            os.path.join(settings.OUTPUT_DIR, filename_only) if settings.OUTPUT_DIR else None,
            os.path.join(settings.IMAGES_DIR, filename_only),
        ])
        # Filter out None values
        potential_paths = [p for p in potential_paths if p is not None]
    
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
        document = db_manager.get_document_by_doc_id(doc_id)
        if not document:
            raise HTTPException(404, detail="Document not found")
        
        print(f"DEBUG: Document retrieved: {document.filename}")
        
        # Check if using database storage
        if pdf_processor.use_database_storage and document.file_id:
            # Serve from database
            try:
                file_content = pdf_processor.get_document_content(doc_id)
                
                # Create streaming response
                def generate():
                    yield file_content
                
                return StreamingResponse(
                    io.BytesIO(file_content),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={document.filename}"}
                )
                
            except Exception as e:
                print(f"DEBUG: Error retrieving document from database: {e}")
                raise HTTPException(500, detail="Error retrieving document from database")
        
        else:
            # Legacy file storage - get document info for file paths
            doc_info = pdf_processor.get_document_info(doc_id)
            pdf_path = doc_info.get("pdf_path")
            
            if not pdf_path:
                raise HTTPException(404, detail="Document file path not found")
            
            print(f"DEBUG: Document pdf_path: {pdf_path}")
            print(f"DEBUG: File exists at pdf_path: {os.path.exists(pdf_path)}")
            
            # First, try the stored path as-is
            if validate_file_path(pdf_path, settings.DOCS_DIR):
                filename = os.path.basename(pdf_path)
                print(f"DEBUG: Returning PDF using stored path: {pdf_path}")
                return FileResponse(pdf_path, filename=filename)
            
            # If that fails, try to find the file by doc_id in our docs directory
            potential_pdf_paths = []
            if settings.DOCS_DIR:
                potential_pdf_paths.append(os.path.join(settings.DOCS_DIR, f"{doc_id}.pdf"))
            if settings.OUTPUT_DIR:
                potential_pdf_paths.append(os.path.join(settings.OUTPUT_DIR, f"{doc_id}.pdf"))
            
            # Also try looking for files that start with the doc_id (for annotation outputs)
            if settings.OUTPUT_DIR and os.path.exists(settings.OUTPUT_DIR):
                for filename in os.listdir(settings.OUTPUT_DIR):
                    if filename.startswith(doc_id) and filename.endswith('.pdf'):
                        potential_pdf_paths.append(os.path.join(settings.OUTPUT_DIR, filename))
            
            if settings.DOCS_DIR and os.path.exists(settings.DOCS_DIR):
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
            
    except FileNotFoundError:
        print(f"DEBUG: Document {doc_id} not found in database")
        raise HTTPException(404, detail="Document not found")
    except Exception as e:
        print(f"DEBUG: Error in download_pdf: {e}")
        raise HTTPException(500, detail="Internal server error")

@router.get("/download/output/{output_id}")
async def download_generated_output(output_id: str):
    """
    Download a generated output file by output ID
    """
    print(f"DEBUG: Generated output download request for output_id: {output_id}")
    
    if not pdf_processor.use_database_storage:
        raise HTTPException(501, detail="Generated output downloads only available with database storage")
    
    try:
        output_dict = pdf_processor.get_generated_output(output_id)
        
        # Create streaming response
        return StreamingResponse(
            io.BytesIO(output_dict['file_data']),
            media_type=output_dict['content_type'],
            headers={"Content-Disposition": f"attachment; filename={output_dict['filename']}"}
        )
        
    except FileNotFoundError:
        print(f"DEBUG: Generated output {output_id} not found")
        raise HTTPException(404, detail="Generated output not found")
    except Exception as e:
        print(f"DEBUG: Error downloading generated output: {e}")
        raise HTTPException(500, detail="Error downloading generated output")

@router.get("/outputs/user/{user_id}")
async def list_user_generated_outputs(user_id: int):
    """
    List all generated outputs for a user
    """
    if not pdf_processor.use_database_storage:
        raise HTTPException(501, detail="Generated output listing only available with database storage")
    
    try:
        outputs = pdf_processor.list_user_generated_outputs(user_id)
        return {
            "user_id": user_id,
            "outputs": outputs,
            "count": len(outputs)
        }
    except Exception as e:
        print(f"DEBUG: Error listing user outputs: {e}")
        raise HTTPException(500, detail="Error listing generated outputs")
