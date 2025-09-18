#!/usr/bin/env python3
"""
Standalone debug server to test FastAPI functionality
"""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Debug Server",
    description="Standalone debug server",
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
        "service": "Debug Server"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    logger.info("🏥 HEALTH CHECK ENDPOINT HIT!")
    print("🏥 HEALTH CHECK ENDPOINT HIT!")
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0-debug"
    }


@app.get("/test")
async def test_endpoint():
    """Simple test endpoint"""
    logger.info("🧪 TEST ENDPOINT HIT!")
    print("🧪 TEST ENDPOINT HIT!")
    return {
        "status": "test_success",
        "message": "Debug server is working!",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/webhook")
async def handle_webhook_simple(request: Request):
    """Simplified webhook endpoint"""
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
            logger.info(f"📦 Body parsed successfully - Keys: {list(body_data.keys())}")
            print(f"📦 Body parsed successfully - Keys: {list(body_data.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error: {e}")
            print(f"❌ JSON decode error: {e}")
            return {"error": "Invalid JSON"}

        return {
            "status": "success",
            "message": "Webhook received successfully",
            "received_keys": list(body_data.keys()),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"💥 Webhook error: {e}")
        print(f"💥 Webhook error: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    print("🚀 Starting standalone debug server...")
    print("📍 Server will be available at: http://localhost:8002")
    print("🔧 Press Ctrl+C to stop")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )