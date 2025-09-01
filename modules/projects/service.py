"""
Project management service for the Floor Plan Agent API
"""
import uuid
from typing import List, Optional, Dict, Any
from modules.database.models import db_manager, Project
from modules.pdf_processing.service import pdf_processor

class ProjectService:
    """Project management service"""
    
    def __init__(self):
        self.db = db_manager
    
    def create_project_with_pdf(self, name: str, description: str, user_id: int, 
                               file_content: bytes, filename: str) -> Dict[str, Any]:
        """Create a new project with an associated PDF document"""
        # Generate unique project ID
        project_id = uuid.uuid4().hex
        
        try:
            # First upload and index the PDF
            pdf_result = pdf_processor.upload_and_index_pdf(file_content, filename)
            doc_id = pdf_result["doc_id"]
            
            # Create the project with the document ID
            db_project_id = self.db.create_project(
                project_id=project_id,
                name=name,
                description=description,
                user_id=user_id,
                doc_id=doc_id
            )
            
            if db_project_id is None:
                raise ValueError("Failed to create project in database")
            
            # Return comprehensive project information
            return {
                "project_id": project_id,
                "name": name,
                "description": description,
                "user_id": user_id,
                "document": {
                    "doc_id": doc_id,
                    "filename": pdf_result["filename"],
                    "pages": pdf_result["pages"],
                    "chunks_indexed": pdf_result["chunks_indexed"]
                },
                "created_at": "just created"
            }
            
        except Exception as e:
            # If PDF upload failed or project creation failed, clean up
            raise ValueError(f"Project creation failed: {str(e)}")
    
    def create_project_without_pdf(self, name: str, description: str, user_id: int) -> Dict[str, Any]:
        """Create a new project without an initial PDF document"""
        # Generate unique project ID
        project_id = uuid.uuid4().hex
        
        try:
            # Create the project without a document
            db_project_id = self.db.create_project(
                project_id=project_id,
                name=name,
                description=description,
                user_id=user_id,
                doc_id=None
            )
            
            if db_project_id is None:
                raise ValueError("Failed to create project in database")
            
            # Return project information
            return {
                "project_id": project_id,
                "name": name,
                "description": description,
                "user_id": user_id,
                "document": None,
                "created_at": "just created"
            }
            
        except Exception as e:
            raise ValueError(f"Project creation failed: {str(e)}")
    
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project information by project ID"""
        project = self.db.get_project_by_id(project_id)
        if not project:
            return None
        
        # Get document information if associated
        document_info = None
        if project.doc_id:
            try:
                document_info = pdf_processor.get_document_info(project.doc_id)
            except Exception:
                # Document might have been deleted
                document_info = {"error": "Document not found"}
        
        return {
            "project_id": project.project_id,
            "name": project.name,
            "description": project.description,
            "user_id": project.user_id,
            "document": document_info,
            "created_at": project.created_at,
            "updated_at": project.updated_at
        }
    
    def get_user_projects(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all projects for a user"""
        projects = self.db.get_user_projects(user_id)
        
        result = []
        for project in projects:
            # Get document information if associated
            document_info = None
            if project.doc_id:
                try:
                    document_info = pdf_processor.get_document_info(project.doc_id)
                except Exception:
                    # Document might have been deleted
                    document_info = {"error": "Document not found"}
            
            result.append({
                "project_id": project.project_id,
                "name": project.name,
                "description": project.description,
                "user_id": project.user_id,
                "document": document_info,
                "created_at": project.created_at,
                "updated_at": project.updated_at
            })
        
        return result
    
    def add_document_to_project(self, project_id: str, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Add a PDF document to an existing project"""
        # Check if project exists
        project = self.db.get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        try:
            # Upload and index the PDF
            pdf_result = pdf_processor.upload_and_index_pdf(file_content, filename)
            doc_id = pdf_result["doc_id"]
            
            # Update the project with the document ID
            self.db.update_project_document(project_id, doc_id)
            
            return {
                "project_id": project_id,
                "document": {
                    "doc_id": doc_id,
                    "filename": pdf_result["filename"],
                    "pages": pdf_result["pages"],
                    "chunks_indexed": pdf_result["chunks_indexed"]
                }
            }
            
        except Exception as e:
            raise ValueError(f"Failed to add document to project: {str(e)}")
    
    def update_project(self, project_id: str, name: str = None, description: str = None) -> Dict[str, Any]:
        """Update project details"""
        # Check if project exists
        project = self.db.get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        try:
            # Update the project
            self.db.update_project_details(project_id, name, description)
            
            # Return updated project information
            return self.get_project(project_id)
            
        except Exception as e:
            raise ValueError(f"Failed to update project: {str(e)}")
    
    def validate_project_access(self, project_id: str, user_id: int) -> bool:
        """Check if a user has access to a project"""
        project = self.db.get_project_by_id(project_id)
        return project is not None and project.user_id == user_id

# Global project service instance
project_service = ProjectService()