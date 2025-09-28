"""
Custom exceptions for session management
"""

class SessionError(Exception):
    """Base exception for session-related errors"""
    pass

class SessionNotFoundError(SessionError):
    """Raised when a session is not found"""
    pass

class SessionAccessDeniedError(SessionError):
    """Raised when access to a session is denied"""
    pass

class InvalidContextError(SessionError):
    """Raised when an invalid context is provided"""
    pass

class SessionExpiredError(SessionError):
    """Raised when a session has expired"""
    pass

class SessionCreationError(SessionError):
    """Raised when session creation fails"""
    pass

class ContextValidationError(SessionError):
    """Raised when context validation fails"""
    pass