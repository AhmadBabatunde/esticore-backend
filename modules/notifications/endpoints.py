"""Notification API endpoints"""
from fastapi import APIRouter, HTTPException, Query

from modules.notifications.service import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def get_notifications(
    user_id: int,
    include_read: bool = Query(False),
    limit: int = Query(50, ge=1, le=200)
):
    """Retrieve notifications for a user"""
    try:
        return notification_service.list_notifications(user_id, include_read=include_read, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{notification_id}/read")
async def mark_notification_read(notification_id: int, user_id: int):
    """Mark a notification as read"""
    try:
        return notification_service.mark_as_read(notification_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
