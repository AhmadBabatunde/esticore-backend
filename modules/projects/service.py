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
        """Create a new project with an associated PDF document (backward compatibility)"""
        return self.create_project_with_pdfs(name, description, user_id, [file_content], [filename])
    
    def create_project_without_pdf(self, name: str, description: str, user_id: int) -> Dict[str, Any]:
        """Create a new project without an initial PDF document (backward compatibility)"""
        return self.create_project_without_pdfs(name, description, user_id)
    
    def create_project_with_pdfs(self, name: str, description: str, user_id: int, 
                               file_contents: List[bytes], filenames: List[str]) -> Dict[str, Any]:
        """Create a new project with one or more associated PDF documents"""
        # Generate unique project ID
        project_id = uuid.uuid4().hex
        
        print(f"Debug: create_project_with_pdfs called with {len(file_contents)} files")
        print(f"Debug: filenames: {filenames}")
        
        try:
            # First upload and index all PDFs
            doc_ids = []
            document_info = []
            
            for i, (file_content, filename) in enumerate(zip(file_contents, filenames)):
                print(f"Debug: processing file {i+1}/{len(file_contents)}: {filename}")
                print(f"Debug: file content size: {len(file_content)} bytes")
                
                pdf_result = pdf_processor.upload_and_index_pdf(file_content, filename, user_id)
                print(f"Debug: PDF processed successfully, doc_id: {pdf_result['doc_id']}")
                
                doc_ids.append(pdf_result["doc_id"])
                document_info.append({
                    "doc_id": pdf_result["doc_id"],
                    "filename": pdf_result["filename"],
                    "pages": pdf_result["pages"],
                    "chunks_indexed": pdf_result["chunks_indexed"]
                })
            
            print(f"Debug: All PDFs processed. doc_ids: {doc_ids}")
            
            # Create the project with the document IDs
            db_project_id = self.db.create_project(
                project_id=project_id,
                name=name,
                description=description,
                user_id=user_id,
                doc_ids=doc_ids  # Keep for backward compatibility
            )
            
            print(f"Debug: Project created in database with ID: {db_project_id}")
            
            if db_project_id is None:
                raise ValueError("Failed to create project in database")
            
            # Add documents to project using junction table
            for doc_id in doc_ids:
                self.db.add_document_to_project(project_id, doc_id)
            
            # Return comprehensive project information
            result = {
                "project_id": project_id,
                "name": name,
                "description": description,
                "user_id": user_id,
                "documents": document_info,
                "created_at": "just created"
            }
            
            print(f"Debug: Returning result: {result}")
            return result
            
        except Exception as e:
            print(f"Debug: Exception in create_project_with_pdfs: {e}")
            # If PDF upload failed or project creation failed, clean up
            # Note: This is a simplified cleanup that could be improved
            raise ValueError(f"Project creation failed: {str(e)}")
    
    def create_project_without_pdfs(self, name: str, description: str, user_id: int) -> Dict[str, Any]:
        """Create a new project without any initial PDF documents"""
        # Generate unique project ID
        project_id = uuid.uuid4().hex
        
        try:
            # Create the project without documents
            db_project_id = self.db.create_project(
                project_id=project_id,
                name=name,
                description=description,
                user_id=user_id,
                doc_ids=None
            )
            
            if db_project_id is None:
                raise ValueError("Failed to create project in database")
            
            # Return project information
            return {
                "project_id": project_id,
                "name": name,
                "description": description,
                "user_id": user_id,
                "documents": None,
                "created_at": "just created"
            }
            
        except Exception as e:
            raise ValueError(f"Project creation failed: {str(e)}")
    
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project information by project ID"""
        project = self.db.get_project_by_id(project_id)
        if not project:
            return None
        
        # Get document information from junction table
        documents = self.db.get_project_documents(project_id)
        document_info = []
        
        for doc in documents:
            doc_info = {
                "doc_id": doc.doc_id,
                "filename": doc.filename,
                "pdf_path": doc.pdf_path,
                "vector_path": doc.vector_path,
                "pages": doc.pages,
                "status": doc.status
            }
            document_info.append(doc_info)
        
        return {
            "project_id": project.project_id,
            "name": project.name,
            "description": project.description,
            "user_id": project.user_id,
            "documents": document_info if document_info else None,
            "created_at": project.created_at,
            "updated_at": project.updated_at
        }
    
    def get_user_projects(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all projects for a user"""
        projects = self.db.get_user_projects(user_id)
        
        result = []
        for project in projects:
            # Get document information from junction table
            documents = self.db.get_project_documents(project.project_id)
            document_info = []
            
            for doc in documents:
                doc_info = {
                    "doc_id": doc.doc_id,
                    "filename": doc.filename,
                    "pdf_path": doc.pdf_path,
                    "vector_path": doc.vector_path,
                    "pages": doc.pages,
                    "status": doc.status
                }
                document_info.append(doc_info)
            
            result.append({
                "project_id": project.project_id,
                "name": project.name,
                "description": project.description,
                "user_id": project.user_id,
                "documents": document_info if document_info else None,
                "created_at": project.created_at,
                "updated_at": project.updated_at
            })
        
        return result
    
    def add_document_to_project(self, project_id: str, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Add a PDF document to an existing project (backward compatibility)"""
        return self.add_documents_to_project(project_id, [file_content], [filename])
    
    def add_documents_to_project(self, project_id: str, file_contents: List[bytes], filenames: List[str]) -> Dict[str, Any]:
        """Add one or more PDF documents to an existing project"""
        # Check if project exists
        project = self.db.get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        try:
            # Upload and index all PDFs
            document_info = []
            
            for i, (file_content, filename) in enumerate(zip(file_contents, filenames)):
                pdf_result = pdf_processor.upload_and_index_pdf(file_content, filename, project.user_id)
                
                document_info.append({
                    "doc_id": pdf_result["doc_id"],
                    "filename": pdf_result["filename"],
                    "pages": pdf_result["pages"],
                    "chunks_indexed": pdf_result["chunks_indexed"]
                })
            
            # Update the project with the new document IDs
            # Add documents to junction table
            for doc_info in document_info:
                self.db.add_document_to_project(project_id, doc_info["doc_id"])
            
            # Also update the projects table for backward compatibility
            doc_ids = project.doc_ids if project.doc_ids else []
            for doc_info in document_info:
                if doc_info["doc_id"] not in doc_ids:
                    doc_ids.append(doc_info["doc_id"])
            
            self.db.update_project_document(project_id, doc_ids)
            
            # Return updated project information
            updated_project = self.get_project(project_id)
            
            result = {
                "project_id": project_id,
                "documents": document_info
            }
            return result
            
        except Exception as e:
            raise ValueError(f"Failed to add documents to project: {str(e)}")
    
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
    
    def delete_project(self, project_id: str, user_id: int = None, delete_shared_documents: bool = True) -> Dict[str, Any]:
        """Delete a project and its associated documents
        
        Args:
            project_id: The project to delete
            user_id: User ID for ownership verification (optional)
            delete_shared_documents: Whether to delete documents that might be shared with other projects
        """
        # Check if project exists
        project = self.db.get_project_by_id(project_id)
        if not project:
            raise ValueError("Project not found")
        
        # Verify user access if user_id is provided
        if user_id is not None and project.user_id != user_id:
            raise ValueError("Access denied: You don't own this project")
        
        try:
            # Get all documents associated with this project
            documents = self.db.get_project_documents(project_id)
            
            deleted_documents = []
            failed_document_deletions = []
            skipped_shared_documents = []
            
            # Delete associated documents
            for doc in documents:
                try:
                    # Check if document is shared with other projects
                    doc_projects = self.db.get_document_projects(doc.doc_id)
                    is_shared = len(doc_projects) > 1
                    
                    if is_shared and not delete_shared_documents:
                        # Skip deletion of shared document, just remove from project
                        self.db.remove_document_from_project(project_id, doc.doc_id)
                        skipped_shared_documents.append({
                            "doc_id": doc.doc_id,
                            "filename": doc.filename,
                            "reason": "Document is shared with other projects"
                        })
                    else:
                        # Delete the document completely
                        success = pdf_processor.delete_document_files(doc.doc_id)
                        if success:
                            deleted_documents.append({
                                "doc_id": doc.doc_id,
                                "filename": doc.filename,
                                "was_shared": is_shared
                            })
                        else:
                            failed_document_deletions.append({
                                "doc_id": doc.doc_id,
                                "filename": doc.filename,
                                "error": "Failed to delete document files",
                                "was_shared": is_shared
                            })
                except Exception as e:
                    failed_document_deletions.append({
                        "doc_id": doc.doc_id,
                        "filename": doc.filename,
                        "error": str(e),
                        "was_shared": "unknown"
                    })
            
            # Delete project from database (this will cascade delete project_documents entries)
            project_deleted = self.db.delete_project(project_id)
            
            if not project_deleted:
                raise ValueError("Failed to delete project from database")
            
            return {
                "message": "Project deleted successfully",
                "project_id": project_id,
                "project_name": project.name,
                "deleted_documents": deleted_documents,
                "failed_document_deletions": failed_document_deletions,
                "skipped_shared_documents": skipped_shared_documents,
                "total_documents_processed": len(documents),
                "delete_shared_documents": delete_shared_documents
            }
            
        except Exception as e:
            raise ValueError(f"Failed to delete project: {str(e)}")
    
    def delete_user_projects(self, user_id: int) -> Dict[str, Any]:
        """Delete all projects for a user"""
        try:
            projects = self.db.get_user_projects(user_id)
            
            deleted_projects = []
            failed_project_deletions = []
            total_documents_deleted = 0
            total_document_failures = 0
            
            for project in projects:
                try:
                    result = self.delete_project(project.project_id, user_id)
                    deleted_projects.append({
                        "project_id": project.project_id,
                        "project_name": project.name,
                        "documents_deleted": len(result["deleted_documents"]),
                        "document_failures": len(result["failed_document_deletions"])
                    })
                    total_documents_deleted += len(result["deleted_documents"])
                    total_document_failures += len(result["failed_document_deletions"])
                except Exception as e:
                    failed_project_deletions.append({
                        "project_id": project.project_id,
                        "project_name": project.name,
                        "error": str(e)
                    })
            
            return {
                "message": f"Processed {len(projects)} projects for user {user_id}",
                "user_id": user_id,
                "deleted_projects": deleted_projects,
                "failed_project_deletions": failed_project_deletions,
                "total_documents_deleted": total_documents_deleted,
                "total_document_failures": total_document_failures
            }
            
        except Exception as e:
            raise ValueError(f"Failed to delete user projects: {str(e)}")

# Global project service instance
project_service = ProjectService()