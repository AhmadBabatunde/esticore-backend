"""Notification service"""
from typing import Dict, Any

from modules.database import db_manager


class NotificationService:
    """Service for handling in-app notifications"""

    def __init__(self):
        self.db = db_manager

    def list_notifications(self, user_id: int, include_read: bool = False, limit: int = 50) -> Dict[str, Any]:
        notifications = self.db.get_notifications(user_id, include_read=include_read, limit=limit)

        formatted = []
        for notification in notifications:
            formatted.append({
                "notification_id": notification.id,
                "title": notification.title,
                "message": notification.message,
                "type": notification.notification_type,
                "metadata": notification.metadata,
                "is_read": notification.is_read,
                "created_at": notification.created_at
            })

        return {"notifications": formatted}

    def mark_as_read(self, notification_id: int, user_id: int) -> Dict[str, Any]:
        updated = self.db.mark_notification_read(notification_id, user_id)

        if not updated:
            raise ValueError("Notification not found or already read")

        return {"notification_id": notification_id, "marked_as_read": True}


notification_service = NotificationService()
