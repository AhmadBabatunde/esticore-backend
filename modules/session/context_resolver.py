"""
Context resolution service for session management
"""
from typing import Dict, Any, Tuple, Optional
from fastapi import HTTPException

from modules.database.models import db_manager
from modules.projects.service import project_service
from modules.pdf_processing.service import pdf_processor
from .exceptions import ContextValidationError, InvalidContextError

class ContextResolver:
    """Service for resolving and validating session contexts"""
    
    def __init__(self):
        self.db = db_manager
    
    def resolve_context(self, request_data: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        Resolve context type and context ID from request data
        
        Returns:
            Tuple of (context_type, context_id)
        """
        # Check for project context
        project_id = request_data.get('project_id')
        if project_id:
            return 'PROJECT', project_id
        
        # Check for document context
        doc_id = request_data.get('doc_id')
        if doc_id:
            return 'DOCUMENT', doc_id
        
        # Default to general context
        return 'GENERAL', None
    
    def resolve_context_from_form(self, form_data: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        Resolve context from form data (for FastAPI Form parameters)
        
        Returns:
            Tuple of (context_type, context_id)
        """
        # Check for project context first (project takes precedence over document)
        project_id = form_data.get('project_id')
        if project_id:
            return 'PROJECT', project_id
        
        # Check for document context
        doc_id = form_data.get('doc_id')
        if doc_id:
            return 'DOCUMENT', doc_id
        
        # Default to general context
        return 'GENERAL', None
    
    def resolve_context_from_path(self, path_params: Dict[str, str], query_params: Dict[str, Any] = None) -> Tuple[str, Optional[str]]:
        """
        Resolve context from URL path parameters and query parameters
        
        Returns:
            Tuple of (context_type, context_id)
        """
        # Check path parameters first
        if 'project_id' in path_params:
            return 'PROJECT', path_params['project_id']
        
        if 'doc_id' in path_params:
            return 'DOCUMENT', path_params['doc_id']
        
        # Check query parameters if provided
        if query_params:
            project_id = query_params.get('project_id')
            if project_id:
                return 'PROJECT', project_id
            
            doc_id = query_params.get('doc_id')
            if doc_id:
                return 'DOCUMENT', doc_id
        
        # Default to general context
        return 'GENERAL', None
    
    def validate_context_access(self, user_id: int, context_type: str, context_id: str) -> bool:
        """
        Validate that a user has access to the specified context
        
        Args:
            user_id: The user's ID
            context_type: PROJECT, DOCUMENT, or GENERAL
            context_id: The context identifier (project_id, doc_id, or None)
        
        Returns:
            True if user has access, False otherwise
        """
        if context_type == 'GENERAL':
            # Everyone has access to general context
            return True
        
        elif context_type == 'PROJECT':
            if not context_id:
                return False
            
            # Validate project access
            return project_service.validate_project_access(context_id, user_id)
        
        elif context_type == 'DOCUMENT':
            if not context_id:
                return False
            
            # Validate document access
            try:
                document = self.db.get_document_by_doc_id(context_id)
                return document is not None and document.user_id == user_id
            except Exception:
                return False
        
        else:
            # Invalid context type
            return False
    
    def validate_context_access_with_exception(self, user_id: int, context_type: str, context_id: str):
        """
        Validate context access and raise HTTPException if access is denied
        
        Args:
            user_id: The user's ID
            context_type: PROJECT, DOCUMENT, or GENERAL
            context_id: The context identifier
        
        Raises:
            HTTPException: If access is denied or context is invalid
        """
        if not self.validate_context_access(user_id, context_type, context_id):
            if context_type == 'PROJECT':
                raise HTTPException(
                    status_code=403, 
                    detail=f"Access denied to project {context_id} or project not found"
                )
            elif context_type == 'DOCUMENT':
                raise HTTPException(
                    status_code=403, 
                    detail=f"Access denied to document {context_id} or document not found"
                )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid context type: {context_type}"
                )
    
    def get_context_metadata(self, context_type: str, context_id: str) -> Dict[str, Any]:
        """
        Get metadata for a specific context
        
        Args:
            context_type: PROJECT, DOCUMENT, or GENERAL
            context_id: The context identifier
        
        Returns:
            Dictionary containing context metadata
        """
        if context_type == 'GENERAL':
            return {
                'context_type': 'GENERAL',
                'context_id': None,
                'name': 'General Chat',
                'description': 'General conversation not tied to specific content'
            }
        
        elif context_type == 'PROJECT':
            if not context_id:
                return {}
            
            try:
                project = project_service.get_project(context_id)
                if project:
                    return {
                        'context_type': 'PROJECT',
                        'context_id': context_id,
                        'name': project['name'],
                        'description': project['description'],
                        'documents': project.get('documents', []),
                        'created_at': project.get('created_at'),
                        'updated_at': project.get('updated_at')
                    }
            except Exception as e:
                print(f"Error getting project metadata: {e}")
            
            return {'context_type': 'PROJECT', 'context_id': context_id, 'error': 'Project not found'}
        
        elif context_type == 'DOCUMENT':
            if not context_id:
                return {}
            
            try:
                doc_info = pdf_processor.get_document_info(context_id)
                return {
                    'context_type': 'DOCUMENT',
                    'context_id': context_id,
                    'name': doc_info['filename'],
                    'pages': doc_info['pages'],
                    'status': doc_info['status'],
                    'storage_type': doc_info.get('storage_type', 'filesystem')
                }
            except Exception as e:
                print(f"Error getting document metadata: {e}")
            
            return {'context_type': 'DOCUMENT', 'context_id': context_id, 'error': 'Document not found'}
        
        else:
            return {'error': f'Invalid context type: {context_type}'}
    
    def get_context_display_name(self, context_type: str, context_id: str) -> str:
        """
        Get a human-readable display name for a context
        
        Args:
            context_type: PROJECT, DOCUMENT, or GENERAL
            context_id: The context identifier
        
        Returns:
            Human-readable context name
        """
        if context_type == 'GENERAL':
            return 'General Chat'
        
        elif context_type == 'PROJECT':
            if not context_id:
                return 'Unknown Project'
            
            try:
                project = project_service.get_project(context_id)
                if project:
                    return f"Project: {project['name']}"
            except Exception:
                pass
            
            return f'Project: {context_id[:8]}...'
        
        elif context_type == 'DOCUMENT':
            if not context_id:
                return 'Unknown Document'
            
            try:
                doc_info = pdf_processor.get_document_info(context_id)
                return f"Document: {doc_info['filename']}"
            except Exception:
                pass
            
            return f'Document: {context_id[:8]}...'
        
        else:
            return f'Unknown Context: {context_type}'
    
    def suggest_context_from_message(self, message: str, user_id: int) -> Tuple[str, Optional[str]]:
        """
        Suggest context based on message content analysis
        
        Args:
            message: The user's message
            user_id: The user's ID
        
        Returns:
            Tuple of (suggested_context_type, suggested_context_id)
        """
        message_lower = message.lower()
        
        # Look for project-related keywords
        project_keywords = ['project', 'proj', 'building', 'construction', 'site']
        if any(keyword in message_lower for keyword in project_keywords):
            # Try to find the user's most recent project
            try:
                projects = project_service.get_user_projects(user_id)
                if projects:
                    # Return the most recently updated project
                    most_recent = max(projects, key=lambda p: p.get('updated_at', p.get('created_at', '')))
                    return 'PROJECT', most_recent['project_id']
            except Exception:
                pass
        
        # Look for document-related keywords
        doc_keywords = ['document', 'doc', 'pdf', 'page', 'drawing', 'plan', 'blueprint']
        if any(keyword in message_lower for keyword in doc_keywords):
            # Try to find the user's most recent document
            try:
                documents = pdf_processor.list_documents(user_id)
                if documents:
                    # Return the most recently created document
                    most_recent_doc = max(documents.items(), key=lambda d: d[1].get('created_at', ''))
                    return 'DOCUMENT', most_recent_doc[0]
            except Exception:
                pass
        
        # Default to general context
        return 'GENERAL', None
    
    def is_context_switch(self, current_context: Tuple[str, Optional[str]], new_context: Tuple[str, Optional[str]]) -> bool:
        """
        Determine if there's a context switch between current and new context
        
        Args:
            current_context: Tuple of (context_type, context_id)
            new_context: Tuple of (context_type, context_id)
        
        Returns:
            True if context has changed, False otherwise
        """
        return current_context != new_context

# Global context resolver instance
context_resolver = ContextResolver()