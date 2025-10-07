import os
import logging
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from .services.caption_generation import add_captions_to_video

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Video Caption API",
    description="FFmpeg-based video captioning service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static/videos", exist_ok=True)
app.mount("/videos", StaticFiles(directory="static/videos"), name="videos")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Video Caption API"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@app.post("/caption")
async def add_captions_endpoint(data: dict = Body(...)):
    """
    API endpoint: caption a video from a URL.

    Request body:
    {
        "video_url": "https://example.com/video.mp4",
        "model_size": "small",  # optional: tiny, small, medium, large
        "aspect_ratio": "9:16",  # optional
        "user_id": "user123",  # optional
        "video_id": "video456"  # optional
    }

    Response:
    {
        "url": "https://your-app.railway.app/videos/{uid}_captioned.mp4"
    }
    """
    try:
        video_url = data.get("video_url")
        model_size = data.get("model_size", "small")
        aspect_ratio = data.get("aspect_ratio", "9:16")
        user_id = data.get("user_id", "")
        video_id = data.get("video_id", "")

        if not video_url:
            return JSONResponse(
                {"error": "Missing video_url"},
                status_code=400
            )

        logger.info(f"CAPTION_API: Received caption request for: {video_url}")

        captioned_url = await add_captions_to_video(
            final_video_url=video_url,
            aspect_ratio=aspect_ratio,
            user_id=user_id,
            video_id=video_id
        )

        if captioned_url == video_url:
            logger.warning("CAPTION_API: Caption processing failed, returning original URL")
            return JSONResponse(
                {
                    "url": captioned_url,
                    "status": "failed",
                    "message": "Caption processing failed, returned original video"
                },
                status_code=500
            )

        logger.info(f"CAPTION_API: Success! Captioned URL: {captioned_url}")
        return {"url": captioned_url}

    except Exception as e:
        logger.error(f"CAPTION_API: Error processing request: {e}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
