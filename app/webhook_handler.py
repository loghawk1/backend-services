import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import logging
import sys

import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings

from .models import WebhookData, ExtractedData, TaskStatus, ProcessingStats
from .models import RevisionWebhookData, ExtractedRevisionData
from .models import ExtractedWanData
from .config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('webhook_handler.log')
    ]
)
logger = logging.getLogger(__name__)

class WebhookHandler:
    """Handles webhook processing and task queuing"""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_pool = None
        self.arq_pool = None
        
    async def initialize(self):
        """Initialize Redis connections"""
        try:
            logger.info("REDIS: Initializing Redis connections...")
            # Log Redis URL (mask password for security)
            masked_url = self.settings.redis_url.replace(self.settings.redis_url.split('@')[0].split('//')[1], 'xxx:xxx') if '@' in self.settings.redis_url else self.settings.redis_url
            logger.info(f"REDIS: Redis URL: {masked_url}")
            
            # Initialize Redis connection
            self.redis_pool = redis.ConnectionPool.from_url(
                self.settings.redis_url,
                max_connections=20,
                decode_responses=True
            )
            logger.info("REDIS: Connection pool created")
            
            # Initialize ARQ pool for task queue
            logger.info("REDIS: Creating ARQ pool for task queue...")
            self.arq_pool = await create_pool(RedisSettings.from_dsn(self.settings.redis_url))
            logger.info("REDIS: ARQ pool created successfully")
            
            logger.info("REDIS: All connections initialized successfully!")
            
        except Exception as e:
            logger.error(f"REDIS: Failed to initialize Redis connections: {e}")
            logger.exception("Full traceback:")
            raise
    
    async def cleanup(self):
        """Cleanup connections"""
        logger.info("REDIS: Cleaning up connections...")
        if self.redis_pool:
            logger.info("REDIS: Disconnecting Redis pool...")
            await self.redis_pool.disconnect()
        if self.arq_pool:
            logger.info("REDIS: Closing ARQ pool...")
            await self.arq_pool.close()
        logger.info("REDIS: Cleanup complete")
    
    async def check_redis_connection(self) -> bool:
        """Check if Redis is connected"""
        try:
            logger.info("REDIS: Checking Redis connection...")
            if not self.redis_pool:
                logger.warning("REDIS: Pool not initialized")
                return False
            
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            await redis_client.ping()
            logger.info("REDIS: Ping successful")
            return True
        except Exception as e:
            logger.error(f"REDIS: Connection check failed: {e}")
            return False
    
    async def extract_webhook_data(self, webhook_data: WebhookData) -> Optional[ExtractedData]:
        """Extract required fields from webhook data"""
        try:
            logger.info("EXTRACT: Starting webhook data extraction...")
            body = webhook_data.body
            logger.info(f"EXTRACT: Processing webhook body with {len(body)} fields")
            
            # Extract required fields from the webhook body
            extracted = ExtractedData(
                prompt=body.get("prompt", ""),
                image_url=body.get("image_url", ""),
                video_id=body.get("video_id", ""),
                chat_id=body.get("chat_id", ""),
                user_id=body.get("user_id", ""),
                user_email=body.get("user_email", ""),
                user_name=body.get("user_name", ""),
                is_revision=body.get("is_revision", False),
                request_timestamp=body.get("request_timestamp", ""),
                source=body.get("source", ""),
                version=body.get("version", ""),
                idempotency_key=body.get("idempotency_key", ""),
                callback_url=body.get("callback_url", ""),
                webhook_url=body.get("webhookUrl", ""),
                execution_mode=body.get("executionMode", ""),
                task_id=str(uuid.uuid4())
            )
            logger.info(f"EXTRACT: Generated task ID: {extracted.task_id}")
            
            # Validate that required fields are present
            required_fields = [
                ("prompt", extracted.prompt),
                ("image_url", extracted.image_url),
                ("video_id", extracted.video_id),
                ("user_id", extracted.user_id),
                ("user_email", extracted.user_email)
            ]
            
            missing_fields = [name for name, value in required_fields if not value]
            
            if not all([
                extracted.prompt,
                extracted.image_url,
                extracted.video_id,
                extracted.user_id,
                extracted.user_email
            ]):
                logger.error(f"EXTRACT: Missing required fields: {missing_fields}")
                return None
            
            logger.info(f"EXTRACT: Successfully extracted data:")
            logger.info(f"EXTRACT: Video ID: {extracted.video_id}")
            logger.info(f"EXTRACT: User: {extracted.user_email}")
            logger.info(f"EXTRACT: Prompt length: {len(extracted.prompt)} chars")
            return extracted
            
        except Exception as e:
            logger.error(f"EXTRACT: Failed to extract webhook data: {e}")
            logger.exception("Full traceback:")
            return None
    
    async def extract_revision_data(self, revision_webhook_data: RevisionWebhookData) -> Optional[ExtractedRevisionData]:
        """Extract required fields from revision webhook data"""
        try:
            logger.info("EXTRACT: Starting revision webhook data extraction...")
            body = revision_webhook_data.body
            logger.info(f"EXTRACT: Processing revision webhook body with {len(body)} fields")
            
            # Extract required fields from the revision webhook body
            extracted = ExtractedRevisionData(
                video_id=body.get("video_id", ""),
                parent_video_id=body.get("parent_video_id", ""),
                original_video_id=body.get("original_video_id", ""),
                chat_id=body.get("chat_id", ""),
                user_id=body.get("user_id", ""),  # Use user_id directly, not email
                user_email=body.get("user_email", ""),
                user_name=body.get("user_name", ""),
                revision_request=body.get("revision_request", ""),
                prompt=body.get("prompt", ""),
                image_url=body.get("image_url", ""),
                is_revision=body.get("is_revision", True),
                timestamp=body.get("timestamp", ""),
                callback_url=body.get("callback_url", ""),
                task_id=str(uuid.uuid4())
            )
            logger.info(f"EXTRACT: Generated revision task ID: {extracted.task_id}")
            
            # Validate that required fields are present
            required_fields = [
                ("video_id", extracted.video_id),
                ("parent_video_id", extracted.parent_video_id),
                ("revision_request", extracted.revision_request),
                ("user_email", extracted.user_email),
                ("callback_url", extracted.callback_url)
            ]
            
            missing_fields = [name for name, value in required_fields if not value]
            
            if missing_fields:
                logger.error(f"EXTRACT: Missing required revision fields: {missing_fields}")
                return None
            
            logger.info(f"EXTRACT: Successfully extracted revision data:")
            logger.info(f"EXTRACT: Video ID: {extracted.video_id}")
            logger.info(f"EXTRACT: Parent Video ID: {extracted.parent_video_id}")
            logger.info(f"EXTRACT: User: {extracted.user_email}")
            logger.info(f"EXTRACT: Revision request length: {len(extracted.revision_request)} chars")
            return extracted
            
        except Exception as e:
            logger.error(f"EXTRACT: Failed to extract revision webhook data: {e}")
            logger.exception("Full traceback:")
            return None
    
    async def extract_wan_data(self, webhook_data: WebhookData) -> Optional[ExtractedWanData]:
        """Extract required fields from WAN webhook data"""
        try:
            logger.info("EXTRACT: Starting WAN webhook data extraction...")
            body = webhook_data.body
            logger.info(f"EXTRACT: Processing WAN webhook body with {len(body)} fields")
            # Create a complete dictionary for the ExtractedWanData model
            wan_data_for_model = {
                "prompt": body.get("prompt"),
                "image_url": body.get("image_url"),
                "video_id": body.get("video_id"),
                "chat_id": body.get("chat_id"),
                "user_id": body.get("user_id"),
                "user_email": body.get("user_email"),
                "user_name": body.get("user_name"),
                "model": body.get("model", "wan"),
                "request_timestamp": body.get("request_timestamp"),
                "source": body.get("source"),
                "version": body.get("version"),
                "idempotency_key": body.get("idempotency_key"),
                "callback_url": body.get("callback_url"),
                "webhook_url": body.get("webhookUrl"),
                "execution_mode": body.get("executionMode"),
                "task_id": str(uuid.uuid4())
            }
            
            # Filter out None values for optional fields (keep required fields even if None for Pydantic validation)
            filtered_data = {k: v for k, v in wan_data_for_model.items() if v is not None or k in [
                "prompt", "image_url", "video_id", "user_id", "user_email"
            ]}
            
            logger.info(f"EXTRACT: Filtered WAN data keys: {list(filtered_data.keys())}")
            logger.info(f"EXTRACT: Image URL present: {'image_url' in filtered_data and filtered_data['image_url']}")
            
            # Extract required fields from the webhook body
            extracted = ExtractedWanData(**filtered_data)
            logger.info(f"EXTRACT: Generated WAN task ID: {extracted.task_id}")
            
            # Validate that required fields are present
            required_fields = [
                ("prompt", extracted.prompt),
                ("image_url", extracted.image_url),
                ("video_id", extracted.video_id),
                ("user_id", extracted.user_id),
                ("user_email", extracted.user_email)
            ]
            
            missing_fields = [name for name, value in required_fields if not value]
            
            if not all([
                extracted.prompt,
                extracted.image_url,
                extracted.video_id,
                extracted.user_id,
                extracted.user_email
            ]):
                logger.error(f"EXTRACT: Missing required WAN fields: {missing_fields}")
                return None
            
            logger.info(f"EXTRACT: Successfully extracted WAN data:")
            logger.info(f"EXTRACT: Video ID: {extracted.video_id}")
            logger.info(f"EXTRACT: User: {extracted.user_email}")
            logger.info(f"EXTRACT: Model: {extracted.model}")
            logger.info(f"EXTRACT: Prompt length: {len(extracted.prompt)} chars")
            return extracted
            
        except Exception as e:
            logger.error(f"EXTRACT: Failed to extract WAN webhook data: {e}")
            logger.exception("Full traceback:")
            return None
    
    async def queue_processing_task(self, extracted_data: ExtractedData) -> str:
        """Queue a processing task using ARQ"""
        try:
            logger.info(f"QUEUE: Queuing processing task for video: {extracted_data.video_id}")
            
            # Store task metadata in Redis
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            task_key = f"task:{extracted_data.task_id}"
            task_data = {
                "status": "queued",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "data": json.dumps(extracted_data.dict()),
                "video_id": extracted_data.video_id,
                "user_id": extracted_data.user_id,
                "prompt": extracted_data.prompt[:100] + "..." if len(extracted_data.prompt) > 100 else extracted_data.prompt
            }
            logger.info(f"QUEUE: Storing task metadata in Redis: {task_key}")
            
            await redis_client.hset(task_key, mapping=task_data)
            await redis_client.expire(task_key, 3600)  # Expire after 1 hour
            logger.info("QUEUE: Task metadata stored successfully")
            
            # Queue the task for processing
            logger.info("QUEUE: Enqueueing task for ARQ processing...")
            job = await self.arq_pool.enqueue_job(
                'process_video_request',
                extracted_data.dict(),
                _job_id=extracted_data.task_id
            )
            logger.info(f"QUEUE: Task enqueued with job ID: {job.job_id if job else 'None'}")
            
            # Update statistics
            await self._update_stats("queued")
            logger.info("QUEUE: Statistics updated")
            
            logger.info(f"QUEUE: Task queued successfully: {extracted_data.task_id}")
            return extracted_data.task_id
            
        except Exception as e:
            logger.error(f"QUEUE: Failed to queue processing task: {e}")
            logger.exception("Full traceback:")
            raise
    
    async def queue_revision_task(self, extracted_data: ExtractedRevisionData) -> str:
        """Queue a revision processing task using ARQ"""
        try:
            logger.info(f"QUEUE: Queuing revision processing task for video: {extracted_data.video_id}")
            logger.info(f"QUEUE: Parent video: {extracted_data.parent_video_id}")
            
            # Store task metadata in Redis
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            task_key = f"task:{extracted_data.task_id}"
            task_data = {
                "status": "queued",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "data": json.dumps(extracted_data.dict()),
                "video_id": extracted_data.video_id,
                "parent_video_id": extracted_data.parent_video_id,
                "user_id": extracted_data.user_id,
                "revision_request": extracted_data.revision_request[:100] + "..." if len(extracted_data.revision_request) > 100 else extracted_data.revision_request,
                "type": "revision"
            }
            logger.info(f"QUEUE: Storing revision task metadata in Redis: {task_key}")
            
            await redis_client.hset(task_key, mapping=task_data)
            await redis_client.expire(task_key, 3600)  # Expire after 1 hour
            logger.info("QUEUE: Revision task metadata stored successfully")
            
            # Queue the task for processing
            logger.info("QUEUE: Enqueueing revision task for ARQ processing...")
            job = await self.arq_pool.enqueue_job(
                'process_video_revision',
                extracted_data.dict(),
                _job_id=extracted_data.task_id
            )
            logger.info(f"QUEUE: Revision task enqueued with job ID: {job.job_id if job else 'None'}")
            
            # Update statistics
            await self._update_stats("queued")
            logger.info("QUEUE: Statistics updated")
            
            logger.info(f"QUEUE: Revision task queued successfully: {extracted_data.task_id}")
            return extracted_data.task_id
            
        except Exception as e:
            logger.error(f"QUEUE: Failed to queue revision processing task: {e}")
            logger.exception("Full traceback:")
            raise
    
    async def queue_wan_processing_task(self, extracted_data: ExtractedWanData) -> str:
        """Queue a WAN processing task using ARQ"""
        try:
            logger.info(f"QUEUE: Queuing WAN processing task for video: {extracted_data.video_id}")
            
            # Store task metadata in Redis
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            task_key = f"task:{extracted_data.task_id}"
            task_data = {
                "status": "queued",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "data": json.dumps(extracted_data.dict()),
                "video_id": extracted_data.video_id,
                "user_id": extracted_data.user_id,
                "model": extracted_data.model,
                "prompt": extracted_data.prompt[:100] + "..." if len(extracted_data.prompt) > 100 else extracted_data.prompt,
                "type": "wan"
            }
            logger.info(f"QUEUE: Storing WAN task metadata in Redis: {task_key}")
            
            await redis_client.hset(task_key, mapping=task_data)
            await redis_client.expire(task_key, 3600)  # Expire after 1 hour
            logger.info("QUEUE: WAN task metadata stored successfully")
            
            # Queue the task for processing
            logger.info("QUEUE: Enqueueing WAN task for ARQ processing...")
            job = await self.arq_pool.enqueue_job(
                'process_wan_request',
                extracted_data.dict(),
                _job_id=extracted_data.task_id
            )
            logger.info(f"QUEUE: WAN task enqueued with job ID: {job.job_id if job else 'None'}")
            
            # Update statistics
            await self._update_stats("queued")
            logger.info("QUEUE: Statistics updated")
            
            logger.info(f"QUEUE: WAN task queued successfully: {extracted_data.task_id}")
            return extracted_data.task_id
            
        except Exception as e:
            logger.error(f"QUEUE: Failed to queue WAN processing task: {e}")
            logger.exception("Full traceback:")
            raise
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a processing task"""
        try:
            logger.info(f"STATUS: Getting status for task: {task_id}")
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            task_key = f"task:{task_id}"
            
            task_data = await redis_client.hgetall(task_key)
            
            if not task_data:
                logger.warning(f"STATUS: Task not found: {task_id}")
                return {"status": "not_found"}
            
            status = task_data.get("status", "unknown")
            logger.info(f"STATUS: Task {task_id} status: {status}")
            
            return {
                "status": status,
                "created_at": task_data.get("created_at"),
                "updated_at": task_data.get("updated_at"),
                "result": json.loads(task_data.get("result", "{}")) if task_data.get("result") else None,
                "error": task_data.get("error")
            }
            
        except Exception as e:
            logger.error(f"STATUS: Failed to get task status for {task_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_processing_stats(self) -> ProcessingStats:
        """Get processing statistics"""
        try:
            logger.info("STATS: Retrieving processing statistics...")
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            # Get stats from Redis
            stats_data = await redis_client.hgetall("processing_stats")
            logger.info(f"STATS: Raw stats data: {dict(stats_data) if stats_data else 'No data'}")
            
            stats = ProcessingStats(
                total_requests=int(stats_data.get("total_requests", 0)),
                queued_tasks=int(stats_data.get("queued_tasks", 0)),
                processing_tasks=int(stats_data.get("processing_tasks", 0)),
                completed_tasks=int(stats_data.get("completed_tasks", 0)),
                failed_tasks=int(stats_data.get("failed_tasks", 0)),
                average_processing_time=float(stats_data.get("average_processing_time", 0.0))
            )
            logger.info(f"STATS: Processed stats: Total={stats.total_requests}, Queued={stats.queued_tasks}")
            return stats
            
        except Exception as e:
            logger.error(f"STATS: Failed to get processing stats: {e}")
            return ProcessingStats()
    
    async def _update_stats(self, operation: str):
        """Update processing statistics"""
        try:
            logger.info(f"STATS: Updating stats for operation: {operation}")
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            if operation == "queued":
                await redis_client.hincrby("processing_stats", "total_requests", 1)
                await redis_client.hincrby("processing_stats", "queued_tasks", 1)
            elif operation == "processing":
                await redis_client.hincrby("processing_stats", "queued_tasks", -1)
                await redis_client.hincrby("processing_stats", "processing_tasks", 1)
            elif operation == "completed":
                await redis_client.hincrby("processing_stats", "processing_tasks", -1)
                await redis_client.hincrby("processing_stats", "completed_tasks", 1)
            elif operation == "failed":
                await redis_client.hincrby("processing_stats", "processing_tasks", -1)
                await redis_client.hincrby("processing_stats", "failed_tasks", 1)
            
            logger.info(f"STATS: Updated for: {operation}")
                
        except Exception as e:
            logger.error(f"STATS: Failed to update stats for {operation}: {e}")
