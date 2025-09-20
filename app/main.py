from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import sys

from .models import WebhookData, ExtractedData
from .models import RevisionWebhookData, ExtractedRevisionData
from .webhook_handler import WebhookHandler
from .config import get_settings

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Video Processing Webhook API",
    description="High-performance webhook handler for video processing requests",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize settings and handler
settings = get_settings()
webhook_handler = WebhookHandler()

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    logger.info("STARTUP: Starting FastAPI application...")
    # Mask Redis URL for security in logs
    masked_redis = settings.redis_url.replace(settings.redis_url.split('@')[0].split('//')[1], 'xxx:xxx') if '@' in settings.redis_url else settings.redis_url
    logger.info(f"STARTUP: Settings loaded: Redis={masked_redis}")
    await webhook_handler.initialize()
    logger.info("STARTUP: Application startup complete - Ready to accept requests!")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    logger.info("SHUTDOWN: Shutting down application...")
    await webhook_handler.cleanup()
    logger.info("SHUTDOWN: Application shutdown complete")

@app.get("/")
async def root():
    """Health check endpoint"""
    logger.info("HEALTH: Health check endpoint accessed")
    return {
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Video Processing Webhook API"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    logger.info("HEALTH: Detailed health check requested")
    redis_status = await webhook_handler.check_redis_connection()
    logger.info(f"HEALTH: Redis connection status: {'Connected' if redis_status else 'Disconnected'}")
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "redis_connected": redis_status,
        "version": "1.0.0"
    }

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Main webhook endpoint to handle incoming video processing requests
    Supports high concurrency (1000+ concurrent requests)
    """
    try:
        logger.info("WEBHOOK: Request received")
        
        # Get request data
        raw_body = await request.body()
        headers = dict(request.headers)
        logger.info(f"WEBHOOK: Request headers: {len(headers)} headers received")
        logger.info(f"WEBHOOK: Request body size: {len(raw_body)} bytes")
        
        # Parse JSON body
        try:
            body_data = json.loads(raw_body.decode('utf-8'))
            logger.info(f"WEBHOOK: JSON parsed successfully - Keys: {list(body_data.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"WEBHOOK: Invalid JSON in webhook body: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Create webhook data model
        webhook_data = WebhookData(
            headers=headers,
            body=body_data,
            timestamp=datetime.utcnow()
        )
        logger.info(f"WEBHOOK: Data model created for timestamp: {webhook_data.timestamp}")
        
        # Extract required fields
        logger.info("WEBHOOK: Extracting required fields from webhook data...")
        extracted_data = await webhook_handler.extract_webhook_data(webhook_data)
        
        if not extracted_data:
            logger.error("WEBHOOK: Failed to extract required data - missing fields")
            raise HTTPException(status_code=400, detail="Failed to extract required data from webhook")
        
        logger.info(f"WEBHOOK: Data extracted - Video ID: {extracted_data.video_id}, User: {extracted_data.user_id}")
        
        # Queue the processing task (non-blocking)
        logger.info("WEBHOOK: Queuing processing task...")
        task_id = await webhook_handler.queue_processing_task(extracted_data)
        
        logger.info(f"WEBHOOK: Processed successfully!")
        logger.info(f"WEBHOOK: Task ID: {task_id}")
        logger.info(f"WEBHOOK: Video ID: {extracted_data.video_id}")
        logger.info(f"WEBHOOK: User ID: {extracted_data.user_id}")
        
        return {
            "status": "success",
            "message": "Webhook received and queued for processing",
            "task_id": task_id,
            "video_id": extracted_data.video_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WEBHOOK: Unexpected error processing webhook: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/revision")
async def handle_revision_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Revision webhook endpoint to handle video revision requests
    Processes user feedback and updates existing videos with AI-powered changes
    """
    try:
        logger.info("REVISION: Revision request received")
        
        # Get request data
        raw_body = await request.body()
        headers = dict(request.headers)
        logger.info(f"REVISION: Request headers: {len(headers)} headers received")
        logger.info(f"REVISION: Request body size: {len(raw_body)} bytes")
        
        # Parse JSON body
        try:
            body_data = json.loads(raw_body.decode('utf-8'))
            logger.info(f"REVISION: JSON parsed successfully - Keys: {list(body_data.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"REVISION: Invalid JSON in revision webhook body: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Create revision webhook data model
        revision_webhook_data = RevisionWebhookData(
            headers=headers,
            body=body_data,
            timestamp=datetime.utcnow()
        )
        logger.info(f"REVISION: Data model created for timestamp: {revision_webhook_data.timestamp}")
        
        # Extract required fields
        logger.info("REVISION: Extracting required fields from revision webhook data...")
        extracted_data = await webhook_handler.extract_revision_data(revision_webhook_data)
        
        if not extracted_data:
            logger.error("REVISION: Failed to extract required data - missing fields")
            raise HTTPException(status_code=400, detail="Failed to extract required data from revision webhook")
        
        logger.info(f"REVISION: Data extracted - Video ID: {extracted_data.video_id}, Parent: {extracted_data.parent_video_id}")
        logger.info(f"REVISION: User: {extracted_data.user_email}")
        logger.info(f"REVISION: Revision request: {extracted_data.revision_request[:100]}...")
        
        # Queue the revision processing task (non-blocking)
        logger.info("REVISION: Queuing revision processing task...")
        task_id = await webhook_handler.queue_revision_task(extracted_data)
        
        logger.info(f"REVISION: Processed successfully!")
        logger.info(f"REVISION: Task ID: {task_id}")
        logger.info(f"REVISION: Video ID: {extracted_data.video_id}")
        logger.info(f"REVISION: Parent Video ID: {extracted_data.parent_video_id}")
        
        return {
            "status": "success",
            "message": "Revision webhook received and queued for processing",
            "task_id": task_id,
            "video_id": extracted_data.video_id,
            "parent_video_id": extracted_data.parent_video_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"REVISION: Unexpected error processing revision webhook: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a processing task"""
    try:
        logger.info(f"TASK: Status requested for: {task_id}")
        status = await webhook_handler.get_task_status(task_id)
        logger.info(f"TASK: {task_id} status: {status.get('status', 'unknown')}")
        return {
            "task_id": task_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"TASK: Error getting task status for {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get task status")

@app.get("/stats")
async def get_stats():
    """Get processing statistics"""
    try:
        logger.info("STATS: Processing statistics requested")
        stats = await webhook_handler.get_processing_stats()
        logger.info(f"STATS: Current stats - Total: {stats.total_requests}, Queued: {stats.queued_tasks}, Processing: {stats.processing_tasks}")
        return {
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"STATS: Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,  # Single worker for Windows compatibility
        log_level="info"
    )
