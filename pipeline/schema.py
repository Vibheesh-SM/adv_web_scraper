from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, Optional, List

class Post(BaseModel):
    # Core ingestion fields (contract between collectors & pipeline)
    post_id: str = Field(..., description="Unique platform-native post identifier")
    platform: str = Field(..., description="Source platform: youtube | twitter | facebook")
    text: str = Field(..., description="Cleaned textual content of the post")
    author_id: str = Field(..., description="Unique platform-native author identifier")
    author_name: str = Field(..., description="Display name of the author")
    author_follower_count: int = Field(default=0, description="Follower/subscriber count of the author")
    account_created_at: Optional[datetime] = Field(default=None, description="Timestamp of author account creation")
    published_at: datetime = Field(..., description="Timestamp of post publication")
    url: str = Field(..., description="Direct link to the post")
    engagement: Dict[str, int] = Field(
        default_factory=dict, 
        description="Engagement metrics (likes, shares, comments, views)"
    )
    raw_json: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Full raw JSON response from API/scraper for auditing"
    )

    # Scored fields (computed and populated by the AI scoring pipeline)
    language: Optional[str] = Field(default=None, description="Detected language of the post")
    threat_score: Optional[float] = Field(default=None, description="Composite score between 0.0 and 1.0")
    threat_label: Optional[str] = Field(default=None, description="Primary threat category or classification label")
    sentiment_score: Optional[float] = Field(default=None, description="VADER compound sentiment score (-1 to 1)")
    embedding: Optional[List[float]] = Field(default=None, description="Dense vector embedding representation")
    cib_cluster_id: Optional[int] = Field(default=None, description="ID of coordinated group cluster, if detected")
    flagged: Optional[bool] = Field(default=False, description="True if composite threat score crosses webhook threshold")
    processed_at: Optional[datetime] = Field(default=None, description="Processing timestamp")
