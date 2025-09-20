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
from .services.revision_ai import generate_revised_scenes_with_gpt4
from .services.video_generation import generate_videos_with_fal, compose_final_video
from .services.audio_generation import generate_voiceovers_with_fal
from .services.music_generation import generate_background_music_with_fal, normalize_music_volume, store_music_in_database
from .services.final_composition import compose_final_video_with_audio
from .services.caption_generation import add_captions_to_video
from .services.callback_service import send_video_callback, send_error_callback
from .supabase_client import get_supabase_client
from .services.database_operations import (
    store_scenes_in_supabase,
    update_scenes_with_image_urls,
    update_scenes_with_video_urls,
    update_scenes_with_voiceover_urls,
    get_scenes_for_video,
    get_music_for_video,
    update_video_id_for_scenes,
    update_video_id_for_music,
    update_scenes_with_revised_content
)
from .services.task_utils import update_task_progress
from .services.single_asset_generation import (
    generate_single_voiceover_with_fal,
    generate_single_scene_image_with_fal,
    generate_single_video_with_fal
)

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
            callback_url=callback_url,
            is_revision=False  # Regular video processing
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


async def process_video_revision(ctx, data: Dict[str, Any]) -> Dict[str, Any]:
    """Main video revision processing pipeline"""
    try:
        logger.info("REVISION: Starting video revision processing pipeline...")

        # Extract data
        task_id = data.get("task_id")
        video_id = data.get("video_id")  # New revision video ID
        parent_video_id = data.get("parent_video_id")  # Original video ID to fetch from
        user_id = data.get("user_id")
        revision_request = data.get("revision_request")
        image_url = data.get("image_url")
        callback_url = data.get("callback_url")

        logger.info("REVISION: Processing Details:")
        logger.info(f"REVISION: Task ID: {task_id}")
        logger.info(f"REVISION: New Video ID: {video_id}")
        logger.info(f"REVISION: Parent Video ID: {parent_video_id}")
        logger.info(f"REVISION: User ID: {user_id}")
        logger.info(f"REVISION: Revision Request: {revision_request[:100]}...")

        # 1. Fetch original scenes from database using parent_video_id
        await update_task_progress(task_id, 5, "Fetching original scenes from database")
        original_scenes = await get_scenes_for_video(parent_video_id, user_id)

        if not original_scenes or len(original_scenes) != 5:
            await update_task_progress(task_id, 0, "Failed to fetch original scenes")
            return {"status": "failed", "error": "Failed to fetch original scenes from database"}

        logger.info(f"REVISION: Retrieved {len(original_scenes)} original scenes from database")

        # 2. Update video_id in database from parent_video_id to new video_id
        await update_task_progress(task_id, 10, "Updating video IDs in database")
        scenes_updated = await update_video_id_for_scenes(parent_video_id, video_id, user_id)
        music_updated = await update_video_id_for_music(parent_video_id, video_id, user_id)

        if not scenes_updated:
            await update_task_progress(task_id, 0, "Failed to update scene video IDs")
            return {"status": "failed", "error": "Failed to update scene video IDs"}

        logger.info(f"REVISION: Video IDs updated successfully in database - Scenes: {scenes_updated}, Music: {music_updated}")

        # 3. Generate revised scenes with GPT-4
        await update_task_progress(task_id, 20, "Generating revised scenes with GPT-4")
        revised_scenes = await generate_revised_scenes_with_gpt4(revision_request, original_scenes, openai_client)

        if not revised_scenes or len(revised_scenes) != 5:
            await update_task_progress(task_id, 0, "Failed to generate revised scenes")
            return {"status": "failed", "error": "Failed to generate 5 revised scenes"}

        logger.info(f"REVISION: Generated {len(revised_scenes)} revised scenes")

        # 4. Update database with revised scene content
        await update_task_progress(task_id, 30, "Updating database with revised content")
        if not await update_scenes_with_revised_content(revised_scenes, video_id, user_id):
            await update_task_progress(task_id, 0, "Failed to update database with revised content")
            return {"status": "failed", "error": "Failed to update database with revised content"}

        # 5. Compare original vs revised scenes to identify changes
        await update_task_progress(task_id, 35, "Analyzing changes and planning re-generation")
        
        scenes_needing_voiceover_regen = []
        scenes_needing_visual_regen = []
        music_needs_regen = False

        for i, (original, revised) in enumerate(zip(original_scenes, revised_scenes)):
            scene_number = revised.get("scene_number", i + 1)
            
            # Check if voiceover changed
            original_voiceover = original.get("vioce_over", "")  # Note: matches table column name
            revised_voiceover = revised.get("voiceover", "")
            if original_voiceover != revised_voiceover:
                scenes_needing_voiceover_regen.append((scene_number, revised_voiceover))
                logger.info(f"REVISION: Scene {scene_number} voiceover changed")

            # Check if visual description changed
            original_visual = original.get("visual_description", "")
            revised_visual = revised.get("visual_description", "")
            if original_visual != revised_visual:
                scenes_needing_visual_regen.append((scene_number, revised_visual))
                logger.info(f"REVISION: Scene {scene_number} visual description changed")

            # Check if sound effects or music direction changed
            original_sound = original.get("sound_effects", "")
            revised_sound = revised.get("sound_effects", "")
            original_music_dir = original.get("music_direction", "")
            revised_music_dir = revised.get("music_direction", "")
            
            if original_sound != revised_sound or original_music_dir != revised_music_dir:
                music_needs_regen = True
                logger.info(f"REVISION: Scene {scene_number} sound/music changed - will regenerate background music")

        logger.info(f"REVISION: Analysis complete - Voiceover regen: {len(scenes_needing_voiceover_regen)}, Visual regen: {len(scenes_needing_visual_regen)}, Music regen: {music_needs_regen}")

        # 6. Re-generate voiceovers for changed scenes
        if scenes_needing_voiceover_regen:
            await update_task_progress(task_id, 45, f"Re-generating {len(scenes_needing_voiceover_regen)} voiceovers")
            
            for scene_number, voiceover_text in scenes_needing_voiceover_regen:
                logger.info(f"REVISION: Re-generating voiceover for scene {scene_number}")
                new_voiceover_url = await generate_single_voiceover_with_fal(voiceover_text)
                
                if new_voiceover_url:
                    # Update specific scene's voiceover_url in database
                    supabase = get_supabase_client()
                    result = supabase.table("scenes").update({
                        "voiceover_url": new_voiceover_url,
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("video_id", video_id).eq("user_id", user_id).eq("scene_number", scene_number).execute()
                    
                    if result.data:
                        logger.info(f"REVISION: Scene {scene_number} voiceover URL updated successfully")
                    else:
                        logger.error(f"REVISION: Failed to update scene {scene_number} voiceover URL")
                else:
                    logger.error(f"REVISION: Failed to generate voiceover for scene {scene_number}")

        # 7. Re-generate images and videos for changed visual descriptions
        if scenes_needing_visual_regen:
            await update_task_progress(task_id, 60, f"Re-generating {len(scenes_needing_visual_regen)} scene images and videos")
            
            for scene_number, visual_description in scenes_needing_visual_regen:
                logger.info(f"REVISION: Re-generating image and video for scene {scene_number}")
                
                # Generate new scene image
                new_image_url = await generate_single_scene_image_with_fal(visual_description, image_url)
                
                if new_image_url:
                    # Generate new scene video from the new image
                    new_video_url = await generate_single_video_with_fal(new_image_url, visual_description)
                    
                    if new_video_url:
                        # Update scene's image_url and scene_clip_url in database
                        supabase = get_supabase_client()
                        result = supabase.table("scenes").update({
                            "image_url": new_image_url,
                            "scene_clip_url": new_video_url,
                            "updated_at": datetime.utcnow().isoformat()
                        }).eq("video_id", video_id).eq("user_id", user_id).eq("scene_number", scene_number).execute()
                        
                        if result.data:
                            logger.info(f"REVISION: Scene {scene_number} image and video URLs updated successfully")
                        else:
                            logger.error(f"REVISION: Failed to update scene {scene_number} image and video URLs")
                    else:
                        logger.error(f"REVISION: Failed to generate video for scene {scene_number}")
                else:
                    logger.error(f"REVISION: Failed to generate image for scene {scene_number}")

        # 8. Re-generate background music if needed
        music_url_for_composition = ""
        if music_needs_regen:
            await update_task_progress(task_id, 75, "Re-generating background music")
            
            # Generate new background music using revised scenes
            raw_music_url = await generate_background_music_with_fal(revised_scenes)
            
            if raw_music_url:
                # Normalize music volume
                normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
                
                if normalized_music_url:
                    # Store/update music table with new music URL using upsert
                    music_stored = await store_music_in_database(normalized_music_url, video_id, user_id)
                    
                    if music_stored:
                        logger.info("REVISION: Background music updated successfully")
                        music_url_for_composition = normalized_music_url  # Set for composition
                    else:
                        logger.error("REVISION: Failed to update background music in database")
                else:
                    logger.error("REVISION: Failed to normalize background music")
            else:
                logger.error("REVISION: Failed to generate background music")

        # 9. Fetch all current scene clip URLs and voiceover URLs
        await update_task_progress(task_id, 85, "Fetching updated assets for final composition")
        
        # CRITICAL: Fetch current music URL from database using the updated video_id
        # This will get either the re-associated original music or newly generated music
        current_music = await get_music_for_video(video_id, user_id)
        music_url_for_composition = ""
        if current_music and current_music.get('music_url'):
            music_url_for_composition = current_music.get('music_url')
            logger.info(f"REVISION: Retrieved music URL from database: {music_url_for_composition}")
        else:
            logger.info("REVISION: No music found in database for this video")
        
        # Get updated scenes from database
        updated_scenes = await get_scenes_for_video(video_id, user_id)
        
        if not updated_scenes or len(updated_scenes) != 5:
            await update_task_progress(task_id, 0, "Failed to fetch updated scenes for composition")
            return {"status": "failed", "error": "Failed to fetch updated scenes for final composition"}

        # Extract URLs for composition
        scene_clip_urls = [scene.get("scene_clip_url", "") for scene in updated_scenes]
        voiceover_urls = [scene.get("voiceover_url", "") for scene in updated_scenes]

        logger.info(f"REVISION: Composing final video with {len([url for url in scene_clip_urls if url])} scene clips")
        logger.info(f"REVISION: Using {len([url for url in voiceover_urls if url])} voiceovers")
        logger.info(f"REVISION: Using music: {'Yes' if music_url_for_composition else 'No'}")
        if music_url_for_composition:
            logger.info(f"REVISION: Music URL: {music_url_for_composition}")

        # 10. Compose final video from scene clips
        await update_task_progress(task_id, 90, "Composing final revised video")
        composed_video_url = await compose_final_video(scene_clip_urls)

        if not composed_video_url:
            await update_task_progress(task_id, 0, "Failed to compose final revised video")
            return {"status": "failed", "error": "Failed to compose final revised video"}

        # 11. Compose final video with all audio tracks
        await update_task_progress(task_id, 95, "Adding audio tracks to final video")
        final_video_url = await compose_final_video_with_audio(
            composed_video_url, 
            voiceover_urls, 
            music_url_for_composition
        )

        # 12. Add captions to final video
        await update_task_progress(task_id, 97, "Adding captions to final revised video")
        captioned_video_url = await add_captions_to_video(final_video_url)

        # 13. Final completion
        await update_task_progress(task_id, 100, "Revision processing completed successfully")

        # 14. Send final video to frontend
        logger.info("REVISION: Sending final revised video to frontend...")
        callback_success = await send_video_callback(
            final_video_url=captioned_video_url,
            video_id=video_id,
            chat_id=data.get("chat_id", ""),
            user_id=user_id,
            callback_url=callback_url,
            is_revision=True  # Revision processing
        )
        
        logger.info("REVISION: Video revision processing completed successfully!")
        if callback_success:
            logger.info("REVISION: Frontend callback sent successfully!")
        else:
            logger.warning("REVISION: Frontend callback failed, but processing completed")
        
        return {
            "status": "completed",
            "video_id": video_id,
            "parent_video_id": parent_video_id,
            "revision_request": revision_request,
            "scenes_voiceover_regen": len(scenes_needing_voiceover_regen),
            "scenes_visual_regen": len(scenes_needing_visual_regen),
            "music_regenerated": music_needs_regen,
            "composed_video_url": composed_video_url,
            "final_video_url": final_video_url,
            "captioned_video_url": captioned_video_url,
            "callback_sent": callback_success
        }
        
    except Exception as e:
        logger.error(f"REVISION: Failed to process video revision: {e}")
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
            logger.info("REVISION: Error callback sent to frontend")
        except Exception as callback_error:
            logger.error(f"REVISION: Failed to send error callback: {callback_error}")
        
        await update_task_progress(task_id, 0, f"Revision processing failed: {str(e)}")
        return {"status": "failed", "error": str(e)}
# ARQ Worker Configuration
class WorkerSettings:
    # Use REDIS_URL for Railway compatibility - ensure it's loaded properly
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", settings.redis_url))
    functions = [process_video_request, process_video_revision]
    max_jobs = 10  # Increased from 100 to 10 for better resource management per replica
    job_timeout = 1800  # 30 minutes (1800 seconds) - Fixed timeout for long-running tasks
    
    # Additional ARQ settings for reliability
    keep_result = 3600  # Keep results for 1 hour
    max_tries = 1  # Don't retry failed jobs (they're too expensive)
    retry_delay = 60  # If retrying, wait 1 minute
