import asyncio
import logging
import httpx
from typing import Optional
from ..config import get_settings
from .task_utils import get_resolution_from_aspect_ratio
from .ffmpeg_api_client import submit_caption_task
from .polling_service import poll_caption_task

logger = logging.getLogger(__name__)
settings = get_settings()

async def create_video_with_captions_ffmpeg(video_url: str, model_size: str = "small") -> Optional[str]:
    """
    Create a new video rendering job with captions using FFmpeg API (Whisper).

    Args:
        video_url: The source video URL from final composition
        model_size: Whisper model size (tiny, base, small, medium, large) (default: small)

    Returns:
        task_id (string) if successful, None if failed
    """
    try:
        logger.info("CAPTIONS_FFMPEG: Starting video caption creation with Whisper...")
        logger.info(f"CAPTIONS_FFMPEG: Source video URL: {video_url}")
        logger.info(f"CAPTIONS_FFMPEG: Whisper model size: {model_size}")

        # Validate input
        if not video_url or not video_url.startswith("http"):
            logger.error(f"CAPTIONS_FFMPEG: Invalid video URL: {video_url}")
            return None

        # Submit caption task to FFmpeg API
        task_id = await submit_caption_task(video_url, model_size)

        if not task_id:
            logger.error("CAPTIONS_FFMPEG: Failed to submit caption task")
            return None

        logger.info(f"CAPTIONS_FFMPEG: Caption task submitted successfully - Task ID: {task_id}")
        return task_id

    except Exception as e:
        logger.error(f"CAPTIONS_FFMPEG: Failed to create caption job: {e}")
        logger.exception("Full traceback:")
        return None


async def check_caption_task_status(task_id: str, max_wait_time: int = 600) -> Optional[str]:
    """
    Polls FFmpeg API until the caption task is complete.

    Args:
        task_id: The task ID from create_video_with_captions_ffmpeg
        max_wait_time: Maximum time to wait in seconds (default: 10 minutes)

    Returns:
        Final video URL if successful, None if failed
    """
    try:
        logger.info(f"CAPTIONS_FFMPEG: Checking status for task: {task_id}")
        logger.info(f"CAPTIONS_FFMPEG: Maximum wait time: {max_wait_time} seconds")
        logger.info("CAPTIONS_FFMPEG: Starting immediate polling...")

        # Poll for completion (immediate start, 5-second intervals)
        captioned_video_url = await poll_caption_task(task_id, max_wait_time=max_wait_time)

        if captioned_video_url:
            logger.info("CAPTIONS_FFMPEG: Caption rendering completed successfully!")
            logger.info(f"CAPTIONS_FFMPEG: Final video URL: {captioned_video_url}")
            return captioned_video_url
        else:
            logger.error("CAPTIONS_FFMPEG: Caption rendering failed or timed out")
            return None

    except Exception as e:
        logger.error(f"CAPTIONS_FFMPEG: Failed to check video status: {e}")
        logger.exception("Full traceback:")
        return None


async def add_captions_to_video(final_video_url: str, aspect_ratio: str = "9:16", model_size: str = "small") -> str:
    """
    Complete workflow to add captions to a video using FFmpeg API.

    Args:
        final_video_url: The final composed video URL
        aspect_ratio: Video aspect ratio (e.g., "9:16", "16:9", "1:1", "3:4", "4:3") (not used with FFmpeg)
        model_size: Whisper model size (tiny, base, small, medium, large) (default: small)

    Returns:
        Captioned video URL if successful, original URL if failed
    """
    try:
        logger.info("CAPTIONS_FFMPEG: Starting complete caption workflow with Whisper...")
        logger.info(f"CAPTIONS_FFMPEG: Input video: {final_video_url}")
        logger.info(f"CAPTIONS_FFMPEG: Whisper model: {model_size}")

        # Validate input video URL
        if not final_video_url or not final_video_url.startswith("http"):
            logger.error(f"CAPTIONS_FFMPEG: Invalid input video URL: {final_video_url}")
            return final_video_url

        # Step 1: Create caption job
        logger.info("CAPTIONS_FFMPEG: Step 1 - Creating caption job...")
        task_id = await create_video_with_captions_ffmpeg(final_video_url, model_size)
        if not task_id:
            logger.error("CAPTIONS_FFMPEG: Failed to create caption job, returning original video")
            return final_video_url

        logger.info(f"CAPTIONS_FFMPEG: Caption task created with task ID: {task_id}")

        # Step 2: Wait for completion (immediate polling)
        logger.info("CAPTIONS_FFMPEG: Step 2 - Waiting for caption processing...")
        captioned_video_url = await check_caption_task_status(task_id, max_wait_time=600)  # 10 minutes
        if not captioned_video_url:
            logger.error("CAPTIONS_FFMPEG: Failed to get captioned video, returning original video")
            return final_video_url

        logger.info("CAPTIONS_FFMPEG: Caption workflow completed successfully!")
        logger.info(f"CAPTIONS_FFMPEG: Captioned video URL: {captioned_video_url}")

        # Validate output video URL
        if not captioned_video_url.startswith("http"):
            logger.error(f"CAPTIONS_FFMPEG: Invalid captioned video URL: {captioned_video_url}")
            return final_video_url

        return captioned_video_url

    except Exception as e:
        logger.error(f"CAPTIONS_FFMPEG: Caption workflow failed: {e}")
        logger.exception("Full traceback:")
        return final_video_url  # Return original video as fallback
