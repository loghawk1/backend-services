import logging
from datetime import datetime
import redis.asyncio as redis
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def update_task_progress(task_id: str, progress: int, status: str):
    """Update task progress in Redis"""
    try:
        logger.info(f"PROGRESS: Updating task {task_id}: {progress}% - {status}")

        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
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