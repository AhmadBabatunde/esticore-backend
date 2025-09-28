"""
Session maintenance and cleanup service
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from modules.config.settings import settings
from modules.session.service import session_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SessionMaintenanceService:
    """Service for maintaining and cleaning up sessions"""
    
    def __init__(self):
        self.session_manager = session_manager
        self.is_running = False
        self.cleanup_task = None
    
    async def start_maintenance(self):
        """Start the background maintenance task"""
        if self.is_running:
            logger.warning("Session maintenance is already running")
            return
        
        self.is_running = True
        self.cleanup_task = asyncio.create_task(self._maintenance_loop())
        logger.info("Session maintenance service started")
    
    async def stop_maintenance(self):
        """Stop the background maintenance task"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Session maintenance service stopped")
    
    async def _maintenance_loop(self):
        """Main maintenance loop"""
        cleanup_interval = settings.SESSION_MAINTENANCE_INTERVAL
        
        while self.is_running:
            try:
                await self._perform_maintenance()
                await asyncio.sleep(cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session maintenance: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(300)  # 5 minutes
    
    async def _perform_maintenance(self):
        """Perform maintenance tasks"""
        logger.info("Starting session maintenance")
        
        # Clean up expired sessions
        try:
            cleaned_count = self.session_manager.cleanup_expired_sessions()
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired sessions")
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
        
        # Clear session cache if it's getting too large
        try:
            cache_stats = self.session_manager.get_cache_stats()
            if cache_stats['cache_usage_percent'] > 80:
                logger.info(f"Session cache usage at {cache_stats['cache_usage_percent']:.1f}%, clearing cache")
                self.session_manager.clear_cache()
        except Exception as e:
            logger.error(f"Error managing session cache: {e}")
        
        # Log maintenance statistics
        try:
            stats = await self._get_maintenance_stats()
            logger.info(f"Session maintenance stats: {stats}")
        except Exception as e:
            logger.error(f"Error getting maintenance stats: {e}")
    
    async def _get_maintenance_stats(self) -> Dict[str, Any]:
        """Get maintenance statistics"""
        try:
            # Get cache stats
            cache_stats = self.session_manager.get_cache_stats()
            
            # Get active session count (this would require a new database method)
            # For now, we'll just return cache stats
            return {
                "cache_size": cache_stats["cache_size"],
                "cache_usage_percent": cache_stats["cache_usage_percent"],
                "maintenance_time": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}
    
    def force_cleanup(self, hours: int = None) -> Dict[str, Any]:
        """Force immediate cleanup of expired sessions"""
        try:
            if hours is None:
                hours = settings.SESSION_CLEANUP_HOURS
            
            cleaned_count = self.session_manager.cleanup_expired_sessions(hours)
            
            return {
                "cleaned_sessions": cleaned_count,
                "cleanup_hours": hours,
                "cleanup_time": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error in force cleanup: {e}")
            return {"error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get maintenance service status"""
        return {
            "is_running": self.is_running,
            "cache_stats": self.session_manager.get_cache_stats(),
            "settings": {
                "session_cleanup_hours": settings.SESSION_CLEANUP_HOURS,
                "chat_history_limit": settings.CHAT_HISTORY_LIMIT
            }
        }

# Global maintenance service instance
maintenance_service = SessionMaintenanceService()