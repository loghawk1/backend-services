from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional
from datetime import datetime

class WebhookData(BaseModel):
    """Model for incoming webhook data"""
    headers: Dict[str, str]
    body: Dict[str, Any]
    timestamp: datetime

class ExtractedData(BaseModel):
    """Model for extracted webhook fields"""
    prompt: str = Field(..., description="The prompt content from the webhook body")
    image_url: str = Field(..., description="URL of the product image")
    video_id: str = Field(..., description="Unique video identifier")
    chat_id: str = Field(..., description="Chat session identifier")
    user_id: str = Field(..., description="User identifier")
    user_email: str = Field(..., description="User email address")
    user_name: str = Field(..., description="User name")
    is_revision: bool = Field(default=False, description="Whether this is a revision")
    request_timestamp: str = Field(..., description="Original request timestamp")
    source: str = Field(..., description="Source of the request")
    version: str = Field(..., description="API version")
    idempotency_key: str = Field(..., description="Idempotency key for duplicate detection")
    callback_url: str = Field(..., description="URL to callback when processing is complete")
    webhook_url: str = Field(..., description="Original webhook URL")
    execution_mode: str = Field(..., description="Execution mode (production/development)")
    aspect_ratio: str = Field(default="9:16", description="Aspect ratio for image resizing (e.g., '9:16', '16:9')")
    
    # Additional fields for processing
    task_id: Optional[str] = Field(None, description="Generated task ID")
    processing_status: str = Field(default="queued", description="Current processing status")

class TaskStatus(BaseModel):
    """Model for task status response"""
    task_id: str
    status: str  # queued, processing, completed, failed
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ProcessingStats(BaseModel):
    """Model for processing statistics"""
    total_requests: int = 0
    queued_tasks: int = 0
    processing_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    average_processing_time: float = 0.0

class WanScene(BaseModel):
    """Model for WAN scene structure from GPT-4"""
    scene_number: int = Field(..., description="Scene number (1-6)")
    nano_banana_prompt: str = Field(..., description="Image generation prompt for Nano Banana")
    elevenlabs_prompt: str = Field(..., description="Text-to-speech prompt for ElevenLabs")
    wan2_5_prompt: str = Field(..., description="Video animation prompt for WAN 2.5")

class ExtractedWanData(BaseModel):
    """Model for extracted WAN webhook fields"""
    prompt: str = Field(..., description="The storyboard prompt content from the webhook body")
    image_url: str = Field(..., description="URL of the product image")
    video_id: str = Field(..., description="Unique video identifier")
    chat_id: str = Field(..., description="Chat session identifier")
    user_id: str = Field(..., description="User identifier")
    user_email: str = Field(..., description="User email address")
    user_name: str = Field(..., description="User name")
    model: str = Field(default="wan", description="Model type (should be 'wan')")
    request_timestamp: str = Field(..., description="Original request timestamp")
    source: str = Field(default="web_app", description="Source of the request")
    version: str = Field(..., description="API version")
    idempotency_key: str = Field(..., description="Idempotency key for duplicate detection")
    callback_url: str = Field(..., description="URL to callback when processing is complete")
    webhook_url: str = Field(..., description="Original webhook URL")
    execution_mode: str = Field(..., description="Execution mode (production/development)")
    aspect_ratio: str = Field(default="9:16", description="Aspect ratio for image resizing (e.g., '9:16', '16:9')")
    
    # Additional fields for processing
    task_id: Optional[str] = Field(None, description="Generated task ID")
    processing_status: str = Field(default="queued", description="Current processing status")
class RevisionWebhookData(BaseModel):
    """Model for incoming revision webhook data"""
    headers: Dict[str, str]
    body: Dict[str, Any]
    timestamp: datetime

class ExtractedRevisionData(BaseModel):
    """Model for extracted revision webhook fields"""
    video_id: str = Field(..., description="New revision video identifier (revision_...)")
    parent_video_id: str = Field(..., description="Original video identifier to fetch existing scenes")
    original_video_id: str = Field(..., description="Original video identifier")
    chat_id: str = Field(..., description="Chat session identifier")
    user_id: str = Field(..., description="User identifier")
    user_email: str = Field(..., description="User email address")
    user_name: str = Field(..., description="User name")
    revision_request: str = Field(..., description="User's natural language revision request")
    prompt: str = Field(..., description="Full original prompt content for context")
    image_url: str = Field(..., description="URL of the product image")
    is_revision: bool = Field(default=True, description="Always true for revision requests")
    timestamp: str = Field(..., description="Request timestamp")
    callback_url: str = Field(..., description="URL to callback when processing is complete")
    aspect_ratio: str = Field(default="9:16", description="Aspect ratio for image resizing (e.g., '9:16', '16:9')")
    
    # Additional fields for processing
    task_id: Optional[str] = Field(None, description="Generated task ID")
    processing_status: str = Field(default="queued", description="Current processing status")
