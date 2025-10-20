"""
Optimized project endpoints with async PDF processing
"""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from typing import Optional, List
from modules.projects.service import project_service
from modules.agent.workflow import agent_workflow
from modules.database import db_manager
from modules.session import session_manager
from modules.pdf_processing.service import pdf_processor
from modules.auth.deps import get_current_user_id

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/{project_id}/upload-documents-fast")
async def add_documents_to_project_fast(
    background_tasks: BackgroundTasks,
    project_id: str,
    user_id: int = Depends(get_current_user_id),
    files: List[UploadFile] = File(...)
):
    """
    Add one or more PDF documents to an existing project with optimized performance
    This endpoint uploads files immediately and processes them in the background
    """
    try:
        # Validate project access
        if not project_service.validate_project_access(project_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied or project not found")
        
        # Validate file types
        valid_files = []
        for file in files:
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Only PDF files are allowed")
            valid_files.append(file)
        
        # Quick upload - save files immediately without processing
        uploaded_files = []
        for file in valid_files:
            file_content = await file.read()
            
            # Generate doc_id and save file immediately
            import uuid
            import os
            from modules.config.settings import settings
            
            doc_id = uuid.uuid4().hex
            pdf_path = os.path.join(settings.DOCS_DIR, f"{doc_id}.pdf")
            
            # Save file
            os.makedirs(settings.DOCS_DIR, exist_ok=True)
            with open(pdf_path, "wb") as f:
                f.write(file_content)
            
            uploaded_files.append({
                "doc_id": doc_id,
                "filename": file.filename,
                "pdf_path": pdf_path,
                "status": "uploaded"
            })
        
        # Add background task for processing
        background_tasks.add_task(
            process_uploaded_documents,
            project_id,
            user_id,
            uploaded_files
        )
        
        return {
            "message": "Files uploaded successfully. Processing in background.",
            "project_id": project_id,
            "uploaded_files": len(uploaded_files),
            "files": [{"doc_id": f["doc_id"], "filename": f["filename"], "status": "processing"} for f in uploaded_files]
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document upload failed: {str(e)}")

async def process_uploaded_documents(project_id: str, user_id: int, uploaded_files: List[dict]):
    """Background task to process uploaded documents"""
    try:
        from pypdf import PdfReader
        import os
        
        processed_documents = []
        
        for file_info in uploaded_files:
            try:
                doc_id = file_info["doc_id"]
                filename = file_info["filename"]
                pdf_path = file_info["pdf_path"]
                
                # Read file content for processing
                with open(pdf_path, "rb") as f:
                    file_content = f.read()
                
                # Process the PDF (indexing and vectorization)
                result = pdf_processor.upload_and_index_pdf(file_content, filename, user_id)
                
                # Add to project
                db_manager.add_document_to_project(project_id, doc_id)
                
                processed_documents.append(result)
                
                print(f"✅ Processed document: {filename} ({doc_id})")
                
            except Exception as e:
                print(f"❌ Error processing {file_info['filename']}: {e}")
                # Clean up file if processing failed
                if os.path.exists(file_info["pdf_path"]):
                    os.remove(file_info["pdf_path"])
        
        print(f"✅ Background processing completed for project {project_id}. Processed {len(processed_documents)} documents.")
        
    except Exception as e:
        print(f"❌ Background processing failed for project {project_id}: {e}")

@router.get("/{project_id}/upload-status")
async def get_upload_status(project_id: str, user_id: int = Depends(get_current_user_id)):
    """
    Get the status of document uploads for a project
    """
    try:
        # Validate project access
        if not project_service.validate_project_access(project_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied or project not found")
        
        # Get project with current documents
        project = project_service.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Count documents by status
        documents = project.get("documents", [])
        status_counts = {
            "total": len(documents),
            "active": len([d for d in documents if d.get("status") == "active"]),
            "processing": len([d for d in documents if d.get("status") == "processing"]),
            "error": len([d for d in documents if d.get("status") == "error"])
        }
        
        return {
            "project_id": project_id,
            "status_counts": status_counts,
            "documents": documents
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{project_id}/upload-documents-chunked")
async def upload_documents_chunked(
    project_id: str,
    user_id: int = Depends(get_current_user_id),
    files: List[UploadFile] = File(...)
):
    """
    Upload documents with chunked processing for better performance
    Processes files one by one to avoid memory issues
    """
    try:
        # Validate project access
        if not project_service.validate_project_access(project_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied or project not found")
        
        results = []
        errors = []
        
        for i, file in enumerate(files):
            try:
                if not file.filename.lower().endswith(".pdf"):
                    errors.append({
                        "filename": file.filename,
                        "error": "Only PDF files are allowed",
                        "index": i
                    })
                    continue
                
                # Process one file at a time
                file_content = await file.read()
                
                # Add to project using the service
                result = project_service.add_documents_to_project(
                    project_id=project_id,
                    file_contents=[file_content],
                    filenames=[file.filename]
                )
                
                results.append({
                    "filename": file.filename,
                    "doc_id": result["documents"][0]["doc_id"],
                    "pages": result["documents"][0]["pages"],
                    "chunks_indexed": result["documents"][0]["chunks_indexed"],
                    "status": "completed"
                })
                
                # Reset file position for next iteration
                await file.seek(0)
                
            except Exception as e:
                errors.append({
                    "filename": file.filename,
                    "error": str(e),
                    "index": i
                })
        
        return {
            "project_id": project_id,
            "successful_uploads": results,
            "failed_uploads": errors,
            "total_files": len(files),
            "successful_count": len(results),
            "failed_count": len(errors)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# Add the optimized endpoints to the existing router
from modules.projects.endpoints import router as original_router

# Copy the optimized endpoints to the original router
original_router.add_api_route(
    "/{project_id}/upload-documents-fast",
    add_documents_to_project_fast,
    methods=["POST"]
)

original_router.add_api_route(
    "/{project_id}/upload-status",
    get_upload_status,
    methods=["GET"]
)

original_router.add_api_route(
    "/{project_id}/upload-documents-chunked",
    upload_documents_chunked,
    methods=["POST"]
)