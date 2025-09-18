import asyncio
import logging
import httpx
from typing import Dict, Any
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_video_callback(
        final_video_url: str,
        video_id: str,
        chat_id: str,
        user_id: str,
        callback_url: str = None
) -> bool:
    """
    Send the final video URL to the frontend callback endpoint

    Args:
        final_video_url: The final captioned video URL
        video_id: Video identifier from original webhook
        chat_id: Chat session identifier
        user_id: User identifier
        callback_url: Optional custom callback URL (uses default if not provided)

    Returns:
        True if callback was successful, False otherwise
    """
    try:
        logger.info("CALLBACK: Starting video callback to frontend...")
        logger.info(f"CALLBACK: Final video URL: {final_video_url}")
        logger.info(f"CALLBACK: Video ID: {video_id}")
        logger.info(f"CALLBACK: Chat ID: {chat_id}")
        logger.info(f"CALLBACK: User ID: {user_id}")

        # Use provided callback URL or default
        endpoint_url = callback_url or "https://base44.app/api/apps/68b4aa46f5d6326ab93c3ed0/functions/n8nVideoCallback"
        logger.info(f"CALLBACK: Endpoint URL: {endpoint_url}")

        # Prepare multipart form data
        form_data = {
            "video_url": final_video_url,
            "video_id": video_id,
            "chat_id": chat_id,
            "user_id": user_id
        }

        logger.info("CALLBACK: Sending POST request with multipart form data...")

        # Send POST request with multipart form data
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint_url,
                data=form_data,  # httpx automatically sets Content-Type to multipart/form-data
                headers={
                    "User-Agent": "FastAPI-Video-Processor/1.0"
                }
            )

            # Log response details
            logger.info(f"CALLBACK: Response status: {response.status_code}")
            logger.info(f"CALLBACK: Response headers: {dict(response.headers)}")

            if response.status_code == 200:
                logger.info("CALLBACK: Video callback sent successfully!")
                logger.info(f"CALLBACK: Response content: {response.text[:200]}...")
                return True
            else:
                logger.error(f"CALLBACK: Callback failed with status {response.status_code}")
                logger.error(f"CALLBACK: Response content: {response.text}")
                return False

    except httpx.TimeoutException:
        logger.error("CALLBACK: Request timed out after 30 seconds")
        return False
    except httpx.HTTPError as e:
        logger.error(f"CALLBACK: HTTP error occurred: {e}")
        return False
    except Exception as e:
        logger.error(f"CALLBACK: Failed to send video callback: {e}")
        logger.exception("Full traceback:")
        return False


async def send_error_callback(
        error_message: str,
        video_id: str,
        chat_id: str,
        user_id: str,
        callback_url: str = None
) -> bool:
    """
    Send error notification to frontend when video processing fails

    Args:
        error_message: Description of the error
        video_id: Video identifier from original webhook
        chat_id: Chat session identifier
        user_id: User identifier
        callback_url: Optional custom callback URL

    Returns:
        True if callback was successful, False otherwise
    """
    try:
        logger.info("CALLBACK: Sending error callback to frontend...")
        logger.info(f"CALLBACK: Error: {error_message}")
        logger.info(f"CALLBACK: Video ID: {video_id}")

        # Use provided callback URL or default
        endpoint_url = callback_url or "https://base44.app/api/apps/68b4aa46f5d6326ab93c3ed0/functions/n8nVideoCallback"

        # Prepare error form data
        form_data = {
            "error": error_message,
            "video_id": video_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "status": "failed"
        }

        logger.info("CALLBACK: Sending error notification...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint_url,
                data=form_data,
                headers={
                    "User-Agent": "FastAPI-Video-Processor/1.0"
                }
            )

            if response.status_code == 200:
                logger.info("CALLBACK: Error callback sent successfully")
                return True
            else:
                logger.error(f"CALLBACK: Error callback failed with status {response.status_code}")
                return False

    except Exception as e:
        logger.error(f"CALLBACK: Failed to send error callback: {e}")
        return False