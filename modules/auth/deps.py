from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from modules.auth.service import auth_service

# Shared HTTP bearer for user endpoints
security = HTTPBearer()

def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """Verify JWT from Authorization header and return user_id."""
    token = credentials.credentials
    user_id = auth_service.verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id
