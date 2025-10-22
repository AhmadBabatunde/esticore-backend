"""
Admin data models for the Floor Plan Agent API
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

class SubscriptionInterval(str, Enum):
    QUARTERLY = "quarterly"
    ANNUAL = "annual"

class FeedbackType(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"

@dataclass
class AdminUser:
    """Admin user data model"""
    id: Optional[int] = None
    username: str = ""
    email: str = ""
    password: str = ""
    is_super_admin: bool = False
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

@dataclass
class SubscriptionPlan:
    """Subscription plan data model"""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    price_quarterly: float = 0.0
    price_annual: float = 0.0
    storage_gb: int = 0
    project_limit: int = 0
    user_limit: int = 1
    action_limit: int = 0
    features: List[str] = None
    is_active: bool = True
    has_free_trial: bool = False
    trial_days: int = 0
    created_at: Optional[datetime] = None

@dataclass
class UserSubscription:
    """User subscription data model"""
    id: Optional[int] = None
    user_id: int = 0
    plan_id: int = 0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True
    interval: SubscriptionInterval = SubscriptionInterval.QUARTERLY
    auto_renew: bool = True
    created_at: Optional[datetime] = None

@dataclass
class UserStorage:
    """User storage usage data model"""
    id: Optional[int] = None
    user_id: int = 0
    used_storage_mb: int = 0
    last_updated: Optional[datetime] = None

@dataclass
class Feedback:
    """User feedback data model"""
    id: Optional[int] = None
    user_id: int = 0
    email: str = ""
    ai_response: str = ""
    rating: FeedbackType = FeedbackType.POSITIVE
    project_name: str = ""
    created_at: Optional[datetime] = None

@dataclass
class AIModel:
    """AI model configuration data model"""
    id: Optional[int] = None
    name: str = ""
    provider: str = ""
    model_name: str = ""
    is_active: bool = False
    config: Dict[str, Any] = None
    created_at: Optional[datetime] = None

@dataclass
class RecentlyViewedProject:
    """Recently viewed project tracking"""
    id: Optional[int] = None
    user_id: int = 0
    project_id: str = ""
    viewed_at: Optional[datetime] = None
    view_count: int = 1