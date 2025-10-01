import asyncio
import logging
import httpx
from typing import Optional
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def create_video_with_captions(video_url: str) -> Optional[str]:
    """
    Create a new video rendering job with captions using JSON2Video API.

    Args:
        video_url: The source video URL from final composition

    Returns:
        project_id (string) if successful, None if failed
    """
    try:
        logger.info("CAPTIONS: Starting video caption creation...")
        logger.info(f"CAPTIONS: Source video URL: {video_url}")

        if not settings.json2video_api_key:
            logger.error("CAPTIONS: JSON2VIDEO_API_KEY not found in environment variables")
            return None

        headers = {
            "x-api-key": settings.json2video_api_key,
            "Content-Type": "application/json"
        }

        payload = {
            "resolution": "custom",
            "width": 1080,
            "height": 1920,
            "scenes": [
                {
                    "id": "qyjh9lwj",
                    "comment": "Scene 1 with captions",
                    "elements": [
                        {
                            "id": "q6dznzcv",
                            "type": "video",
                            "src": video_url,
                            "resize": "cover"
                        },
                        {
                            "id": "q41n9kxp",
                            "type": "subtitles",
                            "settings": {
                                "style": "classic",
                                "font-family": "Nunito",
                                "font-size": 55,
                                "word-color": "#FFFFFF",
                                "line-color": "#FFFFFF",
                                "shadow-color": "#00000030",
                                "shadow-offset": 0,
                                "outline-width": 4,
                                "outline-color": "#00000020",
                                "max-words-per-line": 5,
                                "position": "custom",
                                "x": 540,
                                "y": 1600
                            },
                            "language": "en"
                        }
                    ]
                }
            ]
        }
        logger.info("CAPTIONS: Sending request to JSON2Video API...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.json2video.com/v2/movies",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

        if not data.get("success"):
            logger.error(f"CAPTIONS: API error: {data}")
            return None

        project_id = data["project"]
        logger.info(f"CAPTIONS: Caption job created successfully - Project ID: {project_id}")
        return project_id

    except Exception as e:
        logger.error(f"CAPTIONS: Failed to create caption job: {e}")
        logger.exception("Full traceback:")
        return None


async def check_video_status(project_id: str, max_wait_time: int = 600) -> Optional[str]:
    """
    Polls JSON2Video API until the video rendering job is complete.

    Args:
        project_id: The project ID from create_video_with_captions
        max_wait_time: Maximum time to wait in seconds (default: 10 minutes)

    Returns:
        Final video URL if successful, None if failed
    """
    try:
        logger.info(f"CAPTIONS: Checking status for project: {project_id}")
        logger.info(f"CAPTIONS: Maximum wait time: {max_wait_time} seconds")

        if not settings.json2video_api_key:
            logger.error("CAPTIONS: JSON2VIDEO_API_KEY not found")
            return None

        headers = {"x-api-key": settings.json2video_api_key}
        start_time = asyncio.get_event_loop().time()
        interval = 10  # Check every 10 seconds

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                # Check if we've exceeded max wait time
                elapsed_time = asyncio.get_event_loop().time() - start_time
                if elapsed_time > max_wait_time:
                    logger.error(f"CAPTIONS: Timeout after {max_wait_time} seconds")
                    return None

                try:
                    response = await client.get(
                        f"https://api.json2video.com/v2/movies?project={project_id}",
                        headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()

                    movie = data.get("movie", {})
                    status = movie.get("status")
                    message = movie.get("message", "")

                    logger.info(f"CAPTIONS: Status [{status}] - {message}")

                    if status == "done":
                        video_url = movie.get("url")
                        subtitle_url = movie.get("ass")

                        if video_url:
                            logger.info("CAPTIONS: Caption rendering completed successfully!")
                            logger.info(f"CAPTIONS: Final video URL: {video_url}")
                            if subtitle_url:
                                logger.info(f"CAPTIONS: Subtitle file: {subtitle_url}")
                            return video_url
                        else:
                            logger.error("CAPTIONS: No video URL in completed response")
                            return None

                    elif status == "error":
                        logger.error(f"CAPTIONS: Rendering error: {message}")
                        return None

                    elif status in ["pending", "running"]:
                        logger.info(f"CAPTIONS: Still processing... ({status})")
                        await asyncio.sleep(interval)
                        continue

                    else:
                        logger.warning(f"CAPTIONS: Unknown status: {status}")
                        await asyncio.sleep(interval)
                        continue

                except httpx.HTTPError as e:
                    logger.error(f"CAPTIONS: HTTP error checking status: {e}")
                    await asyncio.sleep(interval)
                    continue

    except Exception as e:
        logger.error(f"CAPTIONS: Failed to check video status: {e}")
        logger.exception("Full traceback:")
        return None


async def add_captions_to_video(final_video_url: str) -> str:
    """
    Complete workflow to add captions to a video.

    Args:
        final_video_url: The final composed video URL

    Returns:
        Captioned video URL if successful, original URL if failed
    """
    try:
        logger.info("CAPTIONS: Starting complete caption workflow...")
        logger.info(f"CAPTIONS: Input video: {final_video_url}")

        # Step 1: Create caption job
        project_id = await create_video_with_captions(final_video_url)
        if not project_id:
            logger.error("CAPTIONS: Failed to create caption job, returning original video")
            return final_video_url

        # Step 2: Wait for completion
        captioned_video_url = await check_video_status(project_id, max_wait_time=600)  # 10 minutes
        if not captioned_video_url:
            logger.error("CAPTIONS: Failed to get captioned video, returning original video")
            return final_video_url

        logger.info("CAPTIONS: Caption workflow completed successfully!")
        logger.info(f"CAPTIONS: Captioned video URL: {captioned_video_url}")
        return captioned_video_url

    except Exception as e:
        logger.error(f"CAPTIONS: Caption workflow failed: {e}")
        logger.exception("Full traceback:")
        return final_video_url  # Return original video as fallback
