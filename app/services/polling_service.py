import asyncio
import logging
from typing import Optional, Tuple
from .ffmpeg_api_client import poll_task_status

logger = logging.getLogger(__name__)


async def poll_ffmpeg_task(
    task_id: str,
    task_type: str = "unknown",
    poll_interval: int = 5,
    max_wait_time: int = 600
) -> Optional[str]:
    """
    Generic polling function for any FFmpeg API task with immediate start.

    Args:
        task_id: The task ID from submission
        task_type: Type of task (merge, caption, background-music) for logging
        poll_interval: Seconds between status checks (default: 5)
        max_wait_time: Maximum time to wait in seconds (default: 600 = 10 minutes)

    Returns:
        video_url if successful, None if failed
    """
    try:
        logger.info(f"POLLING: Starting immediate polling for {task_type} task {task_id}")
        logger.info(f"POLLING: Configuration - Interval: {poll_interval}s, Max wait: {max_wait_time}s")

        # Start polling immediately (no initial delay)
        video_url, error = await poll_task_status(task_id, poll_interval, max_wait_time)

        if video_url:
            logger.info(f"POLLING: {task_type} task completed successfully!")
            logger.info(f"POLLING: Result URL: {video_url}")
            return video_url
        else:
            logger.error(f"POLLING: {task_type} task failed: {error}")
            return None

    except Exception as e:
        logger.error(f"POLLING: Failed to poll {task_type} task {task_id}: {e}")
        logger.exception("Full traceback:")
        return None


async def poll_merge_task(
    task_id: str,
    max_wait_time: int = 600
) -> Optional[str]:
    """
    Poll a merge task with optimized settings.

    Args:
        task_id: The merge task ID
        max_wait_time: Maximum time to wait in seconds (default: 600 = 10 minutes)

    Returns:
        video_url if successful, None if failed
    """
    logger.info("POLLING: Starting merge task polling (immediate start)")
    return await poll_ffmpeg_task(
        task_id=task_id,
        task_type="merge",
        poll_interval=5,  # Check every 5 seconds
        max_wait_time=max_wait_time
    )


async def poll_background_music_task(
    task_id: str,
    max_wait_time: int = 300
) -> Optional[str]:
    """
    Poll a background music task with optimized settings.

    Args:
        task_id: The background music task ID
        max_wait_time: Maximum time to wait in seconds (default: 300 = 5 minutes)

    Returns:
        video_url if successful, None if failed
    """
    logger.info("POLLING: Starting background music task polling (immediate start)")
    return await poll_ffmpeg_task(
        task_id=task_id,
        task_type="background-music",
        poll_interval=5,  # Check every 5 seconds
        max_wait_time=max_wait_time
    )


async def poll_caption_task(
    task_id: str,
    max_wait_time: int = 600
) -> Optional[str]:
    """
    Poll a caption task with optimized settings.

    Args:
        task_id: The caption task ID
        max_wait_time: Maximum time to wait in seconds (default: 600 = 10 minutes)

    Returns:
        video_url if successful, None if failed
    """
    logger.info("POLLING: Starting caption task polling (immediate start)")
    return await poll_ffmpeg_task(
        task_id=task_id,
        task_type="caption",
        poll_interval=5,  # Check every 5 seconds
        max_wait_time=max_wait_time
    )
