"""
Session management API endpoints
"""
from fastapi import APIRouter, HTTPException, Form, Depends
from typing import Dict, Any

from modules.session import session_manager, maintenance_service
from modules.session.exceptions import (
    SessionError, SessionNotFoundError, SessionAccessDeniedError,
    InvalidContextError, SessionExpiredError
)

router = APIRouter(prefix="/sessions", tags=["sessions"])
from modules.auth.deps import get_current_user_id

@router.get("/status")
async def get_session_status():
    """Get session management status and statistics"""
    try:
        return {
            "session_manager": {
                "cache_stats": session_manager.get_cache_stats()
            },
            "maintenance_service": maintenance_service.get_status()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting session status: {str(e)}")

@router.post("/cleanup")
async def force_session_cleanup(hours: int = Form(None)):
    """Force immediate cleanup of expired sessions"""
    try:
        result = maintenance_service.force_cleanup(hours)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during session cleanup: {str(e)}")

@router.get("/user/{user_id}")
async def get_user_sessions(user_id: int, current_user_id: int = Depends(get_current_user_id)):
    """Get all active sessions for a user"""
    try:
        # Ensure the caller is the same user or has admin privileges (admin checks can be added later)
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Access denied to requested user's sessions")
        sessions = session_manager.get_active_sessions(user_id)
        return {
            "user_id": user_id,
            "active_sessions": [
                {
                    "session_id": session.session_id,
                    "context_type": session.context_type,
                    "context_id": session.context_id,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                    "last_activity": session.last_activity.isoformat() if session.last_activity else None
                }
                for session in sessions
            ],
            "total_sessions": len(sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user sessions: {str(e)}")

@router.get("/user/{user_id}/context/{context_type}")
async def get_user_context_sessions(user_id: int, context_type: str, current_user_id: int = Depends(get_current_user_id)):
    """Get active sessions for a user filtered by context type"""
    try:
        if context_type not in ['PROJECT', 'DOCUMENT', 'GENERAL']:
            raise HTTPException(status_code=400, detail="Invalid context_type. Must be PROJECT, DOCUMENT, or GENERAL")
        # Ensure the caller is the same user
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Access denied to requested user's sessions")
        sessions = session_manager.get_active_sessions(user_id, context_type)
        return {
            "user_id": user_id,
            "context_type": context_type,
            "active_sessions": [
                {
                    "session_id": session.session_id,
                    "context_id": session.context_id,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                    "last_activity": session.last_activity.isoformat() if session.last_activity else None
                }
                for session in sessions
            ],
            "total_sessions": len(sessions)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user context sessions: {str(e)}")

@router.post("/user/{user_id}/session/{session_id}/deactivate")
async def deactivate_session(user_id: int, session_id: str, current_user_id: int = Depends(get_current_user_id)):
    """Deactivate a specific session"""
    try:
        # Ensure the caller is the same user
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Access denied to requested user's session")
        # Validate session access
        if not session_manager.validate_session_access(session_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied to session")
        
        success = session_manager.deactivate_session(session_id)
        if success:
            return {"message": "Session deactivated successfully", "session_id": session_id}
        else:
            raise HTTPException(status_code=404, detail="Session not found or already inactive")
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SessionAccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except SessionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deactivating session: {str(e)}")

@router.get("/session/{session_id}/context")
async def get_session_context(session_id: str, user_id: int = Form(...), current_user_id: int = Depends(get_current_user_id)):
    """Get context information for a session"""
    try:
        # Ensure the caller is the same user
        if user_id != current_user_id:
            raise HTTPException(status_code=403, detail="Access denied to requested session context")
        # Validate session access
        if not session_manager.validate_session_access(session_id, user_id):
            raise HTTPException(status_code=403, detail="Access denied to session")
        
        context_type, context_id = session_manager.get_session_context(session_id)
        if context_type is None:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "session_id": session_id,
            "context_type": context_type,
            "context_id": context_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting session context: {str(e)}")

@router.post("/maintenance/start")
async def start_maintenance():
    """Start the session maintenance service"""
    try:
        await maintenance_service.start_maintenance()
        return {"message": "Session maintenance service started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting maintenance service: {str(e)}")

@router.post("/maintenance/stop")
async def stop_maintenance():
    """Stop the session maintenance service"""
    try:
        await maintenance_service.stop_maintenance()
        return {"message": "Session maintenance service stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping maintenance service: {str(e)}")