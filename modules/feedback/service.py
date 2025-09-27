"""
Feedback services for the Floor Plan Agent API
"""
from typing import Dict, Any, List
from fastapi import HTTPException

from modules.database import db_manager
from modules.feedback.models import FeedbackType

class FeedbackService:
    """Feedback service class"""
    
    def __init__(self):
        self.db = db_manager
    
    def submit_feedback(self, user_id: int, email: str, ai_response: str, 
                       rating: FeedbackType, project_name: str = None) -> Dict[str, Any]:
        """Submit user feedback"""
        try:
            feedback_id = self.db.create_feedback(
                user_id, email, ai_response, rating.value, project_name
            )
            
            return {
                "message": "Feedback submitted successfully",
                "feedback_id": feedback_id,
                "rating": rating.value,
                "project_name": project_name
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error submitting feedback: {str(e)}")
    
    def get_user_feedback(self, user_id: int, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get user's feedback history"""
        try:
            feedback = self.db.get_all_feedback(page, limit)
            user_feedback = [fb for fb in feedback if fb.user_id == user_id]
            
            return {
                "feedback": user_feedback,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": len(user_feedback)
                }
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching feedback: {str(e)}")
    
    def get_feedback_statistics(self) -> Dict[str, Any]:
        """Get feedback statistics"""
        try:
            stats = self.db.get_feedback_statistics()
            total = stats.get('total', 0)
            positive = stats.get('positive', 0)
            negative = stats.get('negative', 0)
            
            positive_percentage = (positive / total * 100) if total > 0 else 0
            negative_percentage = (negative / total * 100) if total > 0 else 0
            
            return {
                "total_feedback": total,
                "positive": positive,
                "negative": negative,
                "positive_percentage": round(positive_percentage, 2),
                "negative_percentage": round(negative_percentage, 2)
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching feedback statistics: {str(e)}")

# Global feedback service instance
feedback_service = FeedbackService()