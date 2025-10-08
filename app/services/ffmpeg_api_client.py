import asyncio
import logging
import httpx
from typing import Optional, Dict, Any, Tuple
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def normalize_video_url(url: str) -> str:
    """
    Normalize a video URL by ensuring it has the https:// protocol.

    Args:
        url: The video URL to normalize (may or may not have protocol)

    Returns:
        Normalized URL with https:// protocol
    """
    if not url:
        return url

    # If URL already has protocol, return as-is
    if url.startswith("http://") or url.startswith("https://"):
        return url

    # Otherwise, prepend https://
    normalized = f"https://{url}"
    logger.debug(f"FFMPEG_API: Normalized URL: {url} -> {normalized}")
    return normalized


async def submit_merge_task(
    scene_clip_urls: list[str],
    voiceover_urls: list[str],
    width: int = 1080,
    height: int = 1920,
    video_volume: float = 0.2,
    voiceover_volume: float = 2.0
) -> Optional[str]:
    """
    Submit a video merge task to FFmpeg API.

    Args:
        scene_clip_urls: List of scene video URLs
        voiceover_urls: List of voiceover audio URLs (must match scene count)
        width: Output video width in pixels (default: 1080)
        height: Output video height in pixels (default: 1920)
        video_volume: Volume level for video audio (default: 0.2)
        voiceover_volume: Volume level for voiceover (default: 2.0)

    Returns:
        task_id if successful, None if failed
    """
    try:
        logger.info("FFMPEG_API: Submitting merge task...")
        logger.info(f"FFMPEG_API: Scene clips: {len(scene_clip_urls)} videos")
        logger.info(f"FFMPEG_API: Voiceovers: {len(voiceover_urls)} audio files")
        logger.info(f"FFMPEG_API: Output dimensions: {width}x{height}")
        logger.info(f"FFMPEG_API: Volumes - Video: {video_volume}, Voiceover: {voiceover_volume}")

        # Validate inputs
        if len(scene_clip_urls) != len(voiceover_urls):
            logger.error(f"FFMPEG_API: Scene count ({len(scene_clip_urls)}) doesn't match voiceover count ({len(voiceover_urls)})")
            return None

        if not scene_clip_urls or len(scene_clip_urls) == 0:
            logger.error("FFMPEG_API: No scene clips provided")
            return None

        # Prepare payload
        payload = {
            "scene_clip_urls": scene_clip_urls,
            "voiceover_urls": voiceover_urls,
            "width": width,
            "height": height,
            "video_volume": video_volume,
            "voiceover_volume": voiceover_volume
        }

        # Submit task
        url = f"{settings.ffmpeg_api_base_url}/tasks/merge"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        logger.info(f"FFMPEG_API: Merge task submission response: {response.status_code}")

        if response.status_code != 201:
            logger.error(f"FFMPEG_API: Merge task submission failed with status {response.status_code}")
            logger.error(f"FFMPEG_API: Response content: {response.text}")
            return None

        response_data = response.json()
        task_id = response_data.get("task_id")

        if not task_id:
            logger.error(f"FFMPEG_API: No task_id in response: {response_data}")
            return None

        logger.info(f"FFMPEG_API: Merge task submitted successfully - Task ID: {task_id}")
        logger.info(f"FFMPEG_API: Initial status: {response_data.get('status')}")

        return task_id

    except httpx.TimeoutException as e:
        logger.error(f"FFMPEG_API: Timeout submitting merge task: {e}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"FFMPEG_API: HTTP error submitting merge task: {e}")
        return None
    except Exception as e:
        logger.error(f"FFMPEG_API: Failed to submit merge task: {e}")
        logger.exception("Full traceback:")
        return None


async def submit_background_music_task(
    video_url: str,
    music_url: str,
    music_volume: float = 0.3,
    video_volume: float = 1.0
) -> Optional[str]:
    """
    Submit a background music task to FFmpeg API.

    Args:
        video_url: URL of the video to process
        music_url: URL of the background music file
        music_volume: Volume level for background music (default: 0.3)
        video_volume: Volume level for video audio (default: 1.0)

    Returns:
        task_id if successful, None if failed
    """
    try:
        logger.info("FFMPEG_API: Submitting background music task...")
        logger.info(f"FFMPEG_API: Video URL: {video_url}")
        logger.info(f"FFMPEG_API: Music URL: {music_url}")
        logger.info(f"FFMPEG_API: Volumes - Music: {music_volume}, Video: {video_volume}")

        # Normalize and validate inputs
        video_url = normalize_video_url(video_url)
        music_url = normalize_video_url(music_url)

        if not video_url or not video_url.startswith("http"):
            logger.error(f"FFMPEG_API: Invalid video URL: {video_url}")
            return None

        if not music_url or not music_url.startswith("http"):
            logger.error(f"FFMPEG_API: Invalid music URL: {music_url}")
            return None

        # Prepare payload
        payload = {
            "video_url": video_url,
            "music_url": music_url,
            "music_volume": music_volume,
            "video_volume": video_volume
        }

        # Submit task
        url = f"{settings.ffmpeg_api_base_url}/tasks/background-music"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        logger.info(f"FFMPEG_API: Background music task submission response: {response.status_code}")

        if response.status_code != 201:
            logger.error(f"FFMPEG_API: Background music task submission failed with status {response.status_code}")
            logger.error(f"FFMPEG_API: Response content: {response.text}")
            return None

        response_data = response.json()
        task_id = response_data.get("task_id")

        if not task_id:
            logger.error(f"FFMPEG_API: No task_id in response: {response_data}")
            return None

        logger.info(f"FFMPEG_API: Background music task submitted successfully - Task ID: {task_id}")
        logger.info(f"FFMPEG_API: Initial status: {response_data.get('status')}")

        return task_id

    except httpx.TimeoutException as e:
        logger.error(f"FFMPEG_API: Timeout submitting background music task: {e}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"FFMPEG_API: HTTP error submitting background music task: {e}")
        return None
    except Exception as e:
        logger.error(f"FFMPEG_API: Failed to submit background music task: {e}")
        logger.exception("Full traceback:")
        return None


async def submit_caption_task(
    video_url: str,
    model_size: str = "small"
) -> Optional[str]:
    """
    Submit a caption task to FFmpeg API.

    Args:
        video_url: URL of the video to process
        model_size: Whisper model size (tiny, base, small, medium, large) (default: small)

    Returns:
        task_id if successful, None if failed
    """
    try:
        logger.info("FFMPEG_API: Submitting caption task...")
        logger.info(f"FFMPEG_API: Video URL: {video_url}")
        logger.info(f"FFMPEG_API: Whisper model size: {model_size}")

        # Normalize and validate inputs
        video_url = normalize_video_url(video_url)

        if not video_url or not video_url.startswith("http"):
            logger.error(f"FFMPEG_API: Invalid video URL: {video_url}")
            return None

        valid_models = ["tiny", "base", "small", "medium", "large"]
        if model_size not in valid_models:
            logger.warning(f"FFMPEG_API: Invalid model size '{model_size}', using 'small'")
            model_size = "small"

        # Prepare payload
        payload = {
            "video_url": video_url,
            "model_size": model_size
        }

        # Submit task
        url = f"{settings.ffmpeg_api_base_url}/tasks/caption"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        logger.info(f"FFMPEG_API: Caption task submission response: {response.status_code}")

        if response.status_code != 201:
            logger.error(f"FFMPEG_API: Caption task submission failed with status {response.status_code}")
            logger.error(f"FFMPEG_API: Response content: {response.text}")
            return None

        response_data = response.json()
        task_id = response_data.get("task_id")

        if not task_id:
            logger.error(f"FFMPEG_API: No task_id in response: {response_data}")
            return None

        logger.info(f"FFMPEG_API: Caption task submitted successfully - Task ID: {task_id}")
        logger.info(f"FFMPEG_API: Initial status: {response_data.get('status')}")

        return task_id

    except httpx.TimeoutException as e:
        logger.error(f"FFMPEG_API: Timeout submitting caption task: {e}")
        return None
    except httpx.HTTPError as e:
        logger.error(f"FFMPEG_API: HTTP error submitting caption task: {e}")
        return None
    except Exception as e:
        logger.error(f"FFMPEG_API: Failed to submit caption task: {e}")
        logger.exception("Full traceback:")
        return None


async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the status of a task from FFmpeg API.

    Args:
        task_id: The task ID from submission

    Returns:
        Task status dict if successful, None if failed
    """
    try:
        url = f"{settings.ffmpeg_api_base_url}/tasks/{task_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

        if response.status_code != 200:
            logger.error(f"FFMPEG_API: Get task status failed with status {response.status_code}")
            logger.error(f"FFMPEG_API: Response content: {response.text}")
            return None

        return response.json()

    except httpx.HTTPError as e:
        logger.error(f"FFMPEG_API: HTTP error getting task status: {e}")
        return None
    except Exception as e:
        logger.error(f"FFMPEG_API: Failed to get task status: {e}")
        return None


async def poll_task_status(
    task_id: str,
    poll_interval: int = 5,
    max_wait_time: int = 600
) -> Tuple[Optional[str], Optional[str]]:
    """
    Poll task status until completion or failure.

    Args:
        task_id: The task ID from submission
        poll_interval: Seconds between status checks (default: 5)
        max_wait_time: Maximum time to wait in seconds (default: 600 = 10 minutes)

    Returns:
        Tuple of (video_url, error_message). One will be None.
        - (video_url, None) on success
        - (None, error_msg) on failure
    """
    try:
        logger.info(f"FFMPEG_API: Starting polling for task {task_id}")
        logger.info(f"FFMPEG_API: Poll interval: {poll_interval}s, Max wait time: {max_wait_time}s")

        start_time = asyncio.get_event_loop().time()
        check_count = 0

        while True:
            check_count += 1
            elapsed_time = asyncio.get_event_loop().time() - start_time

            # Check timeout
            if elapsed_time > max_wait_time:
                error_msg = f"Task {task_id} timed out after {max_wait_time}s ({check_count} checks)"
                logger.error(f"FFMPEG_API: {error_msg}")
                return None, error_msg

            # Get task status
            logger.info(f"FFMPEG_API: Status check #{check_count} (elapsed: {elapsed_time:.1f}s)")
            status_data = await get_task_status(task_id)

            if not status_data:
                logger.warning(f"FFMPEG_API: Failed to get task status, retrying in {poll_interval}s...")
                await asyncio.sleep(poll_interval)
                continue

            status = status_data.get("status", "unknown")
            video_url = status_data.get("video_url")
            error = status_data.get("error")

            logger.info(f"FFMPEG_API: Status [{status}]")

            if status == "success":
                if video_url:
                    # Normalize the video URL (add https:// if missing)
                    video_url = normalize_video_url(video_url)
                    logger.info(f"FFMPEG_API: Task completed successfully!")
                    logger.info(f"FFMPEG_API: Duration: {elapsed_time:.1f}s")
                    logger.info(f"FFMPEG_API: Video URL: {video_url}")
                    return video_url, None
                else:
                    error_msg = f"Task completed but no video URL in response: {status_data}"
                    logger.error(f"FFMPEG_API: {error_msg}")
                    return None, error_msg

            elif status == "failed":
                error_msg = error or "Task failed with unknown error"
                logger.error(f"FFMPEG_API: Task failed: {error_msg}")
                logger.error(f"FFMPEG_API: Full response: {status_data}")
                return None, error_msg

            elif status in ["queued", "running"]:
                logger.info(f"FFMPEG_API: Task still processing ({status})...")
                await asyncio.sleep(poll_interval)
                continue

            else:
                logger.warning(f"FFMPEG_API: Unknown status '{status}', continuing to poll...")
                await asyncio.sleep(poll_interval)
                continue

    except Exception as e:
        error_msg = f"Failed to poll task status: {e}"
        logger.error(f"FFMPEG_API: {error_msg}")
        logger.exception("Full traceback:")
        return None, error_msg


async def download_video_url(video_url: str) -> Optional[str]:
    """
    Validate and return the video URL from FFmpeg API.

    Args:
        video_url: The video URL from completed task

    Returns:
        video_url if valid, None if invalid
    """
    try:
        if not video_url or not video_url.startswith("http"):
            logger.error(f"FFMPEG_API: Invalid video URL: {video_url}")
            return None

        # Validate URL is accessible
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.head(video_url)

        if response.status_code == 200:
            logger.info(f"FFMPEG_API: Video URL validated successfully: {video_url}")
            return video_url
        else:
            logger.error(f"FFMPEG_API: Video URL not accessible (status {response.status_code}): {video_url}")
            return None

    except Exception as e:
        logger.error(f"FFMPEG_API: Failed to validate video URL: {e}")
        return None
