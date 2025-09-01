"""
Project management API endpoints for the Floor Plan Agent API
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from modules.projects.service import project_service

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("/create")
async def create_project(
    project_name: str = Form(...),
    description: str = Form(...),
    user_id: int = Form(...),
    file: Optional[UploadFile] = File(None)
):
    """
    Create a new project with optional PDF upload
    This endpoint combines project creation with document upload
    """
    try:
        if file:
            # Validate file type
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Only PDF files are allowed")
            
            # Read file content
            file_content = await file.read()
            
            # Create project with PDF
            result = project_service.create_project_with_pdf(
                name=project_name,
                description=description,
                user_id=user_id,
                file_content=file_content,
                filename=file.filename
            )
        else:
            # Create project without PDF
            result = project_service.create_project_without_pdf(
                name=project_name,
                description=description,
                user_id=user_id
            )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project creation failed: {str(e)}")

@router.get("/{project_id}")
async def get_project(project_id: str):
    """
    Get project information by project ID
    """
    try:
        project = project_service.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return project
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/{user_id}")
async def get_user_projects(user_id: int):
    """
    Get all projects for a specific user
    """
    try:
        projects = project_service.get_user_projects(user_id)
        return {"user_id": user_id, "projects": projects}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{project_id}/upload-document")
async def add_document_to_project(
    project_id: str,
    user_id: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Add or replace the PDF document for an existing project
    """
    try:
        # Validate project access
        if not project_service.validate_project_access(project_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied or project not found")
        
        # Validate file type
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Read file content
        file_content = await file.read()
        
        # Add document to project
        result = project_service.add_document_to_project(
            project_id=project_id,
            file_content=file_content,
            filename=file.filename
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document upload failed: {str(e)}")

@router.put("/{project_id}")
async def update_project(
    project_id: str,
    user_id: int = Form(...),
    project_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None)
):
    """
    Update project details (name and/or description)
    """
    try:
        # Validate project access
        if not project_service.validate_project_access(project_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied or project not found")
        
        # Update project
        result = project_service.update_project(
            project_id=project_id,
            name=project_name,
            description=description
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project update failed: {str(e)}")

@router.get("/{project_id}/validate-access/{user_id}")
async def validate_project_access(project_id: str, user_id: int):
    """
    Check if a user has access to a project
    """
    try:
        has_access = project_service.validate_project_access(project_id, user_id)
        return {
            "project_id": project_id,
            "user_id": user_id,
            "has_access": has_access
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))