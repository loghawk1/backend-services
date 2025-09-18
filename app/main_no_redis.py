from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Video Processing Webhook API - No Redis",
    description="Main server without Redis dependencies for debugging",
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


@app.get("/")
async def root():
    """Health check endpoint"""
    logger.info("💓 ROOT ENDPOINT HIT!")
    print("💓 ROOT ENDPOINT HIT!")
    return {
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Video Processing Webhook API - No Redis"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    logger.info("🏥 HEALTH CHECK ENDPOINT HIT!")
    print("🏥 HEALTH CHECK ENDPOINT HIT!")
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0-no-redis"
    }


@app.get("/test")
async def test_endpoint():
    """Simple test endpoint"""
    logger.info("🧪 TEST ENDPOINT HIT!")
    print("🧪 TEST ENDPOINT HIT!")
    return {
        "status": "test_success",
        "message": "Main server (no Redis) is working!",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/webhook")
async def handle_webhook(request: Request):
    """Webhook endpoint without Redis processing"""
    try:
        logger.info("📨 WEBHOOK ENDPOINT HIT!")
        print("📨 WEBHOOK ENDPOINT HIT!")

        # Get request data
        raw_body = await request.body()
        headers = dict(request.headers)

        logger.info(f"📋 Headers: {len(headers)} items")
        print(f"📋 Headers: {len(headers)} items")

        # Parse JSON body
        try:
            body_data = json.loads(raw_body.decode('utf-8'))
            logger.info(f"📦 Body parsed - Video ID: {body_data.get('video_id', 'N/A')}")
            print(f"📦 Body parsed - Video ID: {body_data.get('video_id', 'N/A')}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error: {e}")
            print(f"❌ JSON decode error: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")

        # Simulate task creation
        task_id = f"task-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        logger.info(f"✅ Webhook processed - Task ID: {task_id}")
        print(f"✅ Webhook processed - Task ID: {task_id}")

        return {
            "status": "success",
            "message": "Webhook received (no Redis processing)",
            "task_id": task_id,
            "video_id": body_data.get('video_id'),
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Webhook error: {e}")
        print(f"💥 Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting main server without Redis...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8003,
        log_level="info"
    )