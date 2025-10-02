import logging
from datetime import datetime
import redis.asyncio as redis
from ..config import get_settings
from typing import Tuple

logger = logging.getLogger(__name__)
settings = get_settings()


def get_resolution_from_aspect_ratio(aspect_ratio: str) -> Tuple[int, int]:
    """
    Get video resolution (width, height) based on aspect ratio string
    
    Args:
        aspect_ratio: Aspect ratio string (e.g., "9:16", "16:9", "1:1", "3:4", "4:3")
        
    Returns:
        Tuple of (width, height) for the given aspect ratio
    """
    aspect_ratio_map = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "5:4": (1350, 1080),
        "4:5": (1080, 1350)
    }
    
    # Default to 9:16 if aspect ratio is not recognized
    width, height = aspect_ratio_map.get(aspect_ratio, (1080, 1920))
    
    logger.info(f"RESOLUTION: Aspect ratio '{aspect_ratio}' -> {width}x{height}")
    return width, height


async def update_task_progress(task_id: str, progress: int, status: str):
    """Update task progress in Redis"""
    try:
        logger.info(f"PROGRESS: Updating task {task_id}: {progress}% - {status}")

        redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True
        )

        task_key = f"task:{task_id}"
        await redis_client.hset(task_key, mapping={
            "progress": progress,
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        })

        logger.info("PROGRESS: Task progress updated successfully")

    except Exception as e:
        logger.error(f"PROGRESS: Failed to update task progress: {e}")
