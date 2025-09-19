import os
import asyncio
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import sys

# Third-party imports
from dotenv import load_dotenv
import fal_client
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings
from openai import AsyncOpenAI

# Local imports
from .config import get_settings
from .services.image_processing import resize_image_with_fal, generate_scene_images_with_fal
from .services.scene_generation import generate_scenes_with_gpt4
from .services.video_generation import generate_videos_with_fal, compose_final_video
from .services.audio_generation import generate_voiceovers_with_fal
from .services.music_generation import generate_background_music_with_fal, normalize_music_volume, store_music_in_database
from .services.final_composition import compose_final_video_with_audio
from .services.caption_generation import add_captions_to_video
from .services.callback_service import send_video_callback, send_error_callback
from .services.database_operations import (
    store_scenes_in_supabase,
    update_scenes_with_image_urls,
    update_scenes_with_video_urls,
    update_scenes_with_voiceover_urls
)
from .services.task_utils import update_task_progress

# Load environment variables
load_dotenv()

# Set API key for fal_client
fal_client.api_key = os.getenv("FAL_KEY")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('worker.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize settings and clients
settings = get_settings()
openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

# Log initialization status
logger.info(f"WORKER: Settings loaded - Redis URL configured")
logger.info(f"WORKER: Settings loaded - Redis URL: {settings.redis_url}")

if fal_client.api_key:
    logger.info("WORKER: fal.ai client configured successfully")
    logger.info("WORKER: FAL_KEY loaded: Yes")
else:
    logger.error("WORKER: FAL_KEY not found in environment variables!")
    logger.error("WORKER: FAL_KEY loaded: No")

logger.info("WORKER: OpenAI client configured")


async def process_video_request(ctx, data: Dict[str, Any]) -> Dict[str, Any]:
    """Main video processing pipeline"""
    try:
        logger.info("PIPELINE: Starting video processing pipeline...")

        # Extract data
        task_id = data.get("task_id")
        video_id = data.get("video_id")
        user_id = data.get("user_id")
        prompt = data.get("prompt")
        image_url = data.get("image_url")

        logger.info("PIPELINE: Processing Details:")
        logger.info(f"PIPELINE: Task ID: {task_id}")
        logger.info(f"PIPELINE: Video ID: {video_id}")
        logger.info(f"PIPELINE: User ID: {user_id}")
        logger.info(f"PIPELINE: Prompt: {prompt}")
        logger.info(f"PIPELINE: Image: {image_url}")

        # 1. Resize/reframe original image
        await update_task_progress(task_id, 5, "Resizing image with fal.ai")
        resized_image_url = await resize_image_with_fal(image_url)

        # 2. Generate 5 scenes with GPT-4
        await update_task_progress(task_id, 15, "Generating scenes with GPT-4")
        scenes = await generate_scenes_with_gpt4(prompt, openai_client)

        if not scenes or len(scenes) != 5:
            await update_task_progress(task_id, 0, "Failed to generate scenes")
            return {"status": "failed", "error": "Failed to generate 5 scenes"}

        # 3. Store scenes in database
        await update_task_progress(task_id, 25, "Storing scenes in database")
        if not await store_scenes_in_supabase(scenes, video_id, user_id):
            await update_task_progress(task_id, 0, "Failed to store scenes")
            return {"status": "failed", "error": "Failed to store scenes"}

        # 4. Generate scene images
        await update_task_progress(task_id, 35, "Generating scene images with fal.ai")

        # Add the resized image URL to each scene for Gemini edit model
        scenes_with_image = []
        for scene in scenes:
            scene_with_image = scene.copy()
            scene_with_image["image_urls"] = [resized_image_url]  # Pass resized product image
            scenes_with_image.append(scene_with_image)

        scene_image_urls = await generate_scene_images_with_fal(scenes_with_image)

        if not scene_image_urls or len(scene_image_urls) != 5:
            await update_task_progress(task_id, 0, "Failed to generate scene images")
            return {"status": "failed", "error": "Failed to generate scene images"}

        # 5. Update scenes with image URLs
        await update_task_progress(task_id, 45, "Storing scene image URLs")
        if not await update_scenes_with_image_urls(scene_image_urls, video_id, user_id):
            await update_task_progress(task_id, 0, "Failed to store scene image URLs")
            return {"status": "failed", "error": "Failed to store scene image URLs"}

        # 6. Generate videos from scene images
        await update_task_progress(task_id, 55, "Generating videos from scene images")
        video_urls = await generate_videos_with_fal(scene_image_urls, scenes)

        if not video_urls:
            await update_task_progress(task_id, 0, "Failed to generate videos")
            return {"status": "failed", "error": "Failed to generate videos"}

        # 7. Update scenes with video URLs
        await update_task_progress(task_id, 65, "Storing scene video URLs")
        if not await update_scenes_with_video_urls(video_urls, video_id, user_id):
            await update_task_progress(task_id, 0, "Failed to store scene video URLs")
            return {"status": "failed", "error": "Failed to store scene video URLs"}

        # 8. Compose final video from 5 scene videos
        await update_task_progress(task_id, 75, "Composing final video")
        composed_video_url = await compose_final_video(video_urls)

        if not composed_video_url:
            await update_task_progress(task_id, 0, "Failed to compose final video")
            return {"status": "failed", "error": "Failed to compose final video"}

        # 9. Generate voiceovers for each scene
        await update_task_progress(task_id, 85, "Generating voiceovers")
        voiceover_urls = await generate_voiceovers_with_fal(scenes)

        # 10. Update scenes with voiceover URLs
        await update_task_progress(task_id, 90, "Storing voiceover URLs")
        if voiceover_urls:
            await update_scenes_with_voiceover_urls(voiceover_urls, video_id, user_id)

        # 11. Generate background music
        await update_task_progress(task_id, 92, "Generating background music")
        
        # Make music generation optional - continue pipeline even if it fails
        raw_music_url = ""
        try:
            logger.info("PIPELINE: Starting background music generation (optional step)...")
            raw_music_url = await generate_background_music_with_fal(scenes)
            if raw_music_url:
                logger.info("PIPELINE: Background music generated successfully")
            else:
                logger.warning("PIPELINE: Background music generation failed, continuing without music")
        except Exception as e:
            logger.error(f"PIPELINE: Background music generation failed: {e}")
            logger.info("PIPELINE: Continuing pipeline without background music")

        # 12. Normalize music volume
        normalized_music_url = ""
        if raw_music_url:
            await update_task_progress(task_id, 94, "Normalizing music volume")
            try:
                normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
                logger.info("PIPELINE: Music volume normalized successfully")
            except Exception as e:
                logger.error(f"PIPELINE: Music normalization failed: {e}")
                normalized_music_url = raw_music_url  # Use raw music as fallback
        else:
            logger.info("PIPELINE: Skipping music normalization (no raw music)")

        # 13. Store normalized music in database
        if normalized_music_url:
            await update_task_progress(task_id, 95, "Storing background music")
            try:
                await store_music_in_database(normalized_music_url, video_id, user_id)
                logger.info("PIPELINE: Background music stored in database")
            except Exception as e:
                logger.error(f"PIPELINE: Failed to store music in database: {e}")
        else:
            logger.info("PIPELINE: Skipping music database storage (no music generated)")

        # 14. Final composition with all audio tracks
        await update_task_progress(task_id, 97, "Composing final video with all audio")
        final_video_url = await compose_final_video_with_audio(
            composed_video_url, 
            voiceover_urls, 
            normalized_music_url
        )

        # 15. Add captions to final video
        await update_task_progress(task_id, 98, "Adding captions to final video")
        captioned_video_url = await add_captions_to_video(final_video_url)

        # 16. Final completion
        await update_task_progress(task_id, 100, "Processing completed successfully")

        # 17. Send final video to frontend
        logger.info("PIPELINE: Sending final video to frontend...")
        callback_url = data.get("callback_url")  # Get callback URL from original webhook data
        callback_success = await send_video_callback(
            final_video_url=captioned_video_url,
            video_id=video_id,
            chat_id=data.get("chat_id", ""),
            user_id=user_id,
            callback_url=callback_url
        )
        
        if callback_success:
            logger.info("PIPELINE: Frontend callback sent successfully!")
        else:
            logger.warning("PIPELINE: Frontend callback failed, but processing completed")

        logger.info("PIPELINE: Video processing completed successfully!")

        return {
            "status": "completed",
            "video_id": video_id,
            "resized_image_url": resized_image_url,
            "scene_image_urls": scene_image_urls,
            "video_urls": video_urls,
            "composed_video_url": composed_video_url,
            "voiceover_urls": voiceover_urls,
            "raw_music_url": raw_music_url,
            "normalized_music_url": normalized_music_url,
            "final_video_url": final_video_url,
            "captioned_video_url": captioned_video_url,
            "scenes_count": len(scenes),
            "callback_sent": callback_success
        }

    except Exception as e:
        logger.error(f"PIPELINE: Failed to process video request: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback to frontend
        try:
            callback_url = data.get("callback_url")
            await send_error_callback(
                error_message=str(e),
                video_id=data.get("video_id", ""),
                chat_id=data.get("chat_id", ""),
                user_id=data.get("user_id", ""),
                callback_url=callback_url
            )
            logger.info("PIPELINE: Error callback sent to frontend")
        except Exception as callback_error:
            logger.error(f"PIPELINE: Failed to send error callback: {callback_error}")
        
        await update_task_progress(task_id, 0, f"Processing failed: {str(e)}")
        return {"status": "failed", "error": str(e)}


# ARQ Worker Configuration
class WorkerSettings:
    # Use REDIS_URL for Railway compatibility - ensure it's loaded properly
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", settings.redis_url))
    functions = [process_video_request]
    max_jobs = 10  # Increased from 100 to 10 for better resource management per replica
    job_timeout = 1800  # 30 minutes (1800 seconds) - Fixed timeout for long-running tasks
    
    # Additional ARQ settings for reliability
    keep_result = 3600  # Keep results for 1 hour
    max_tries = 1  # Don't retry failed jobs (they're too expensive)
    retry_delay = 60  # If retrying, wait 1 minute
