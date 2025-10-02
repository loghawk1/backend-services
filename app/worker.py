#!/usr/bin/env python3
"""
ARQ Worker for processing video generation tasks
"""
import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
import fal_client
from openai import AsyncOpenAI
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings

from .config import get_settings
from .models import ExtractedData, ExtractedRevisionData, ExtractedWanData
from .supabase_client import get_supabase_client

# Import all service modules
from .services.scene_generation import generate_scenes_with_gpt4, wan_scene_generator
from .services.image_processing import resize_image_with_fal, generate_scene_images_with_fal
from .services.audio_generation import generate_voiceovers_with_fal
from .services.video_generation import generate_videos_with_fal
from .services.music_generation import generate_background_music_with_fal, normalize_music_volume, store_music_in_database
from .services.final_composition import compose_final_video_with_audio, compose_wan_final_video_with_audio
from .services.caption_generation import add_captions_to_video
from .services.callback_service import send_video_callback, send_error_callback
from .services.database_operations import (
    store_scenes_in_supabase, store_wan_scenes_in_supabase,
    update_scenes_with_image_urls, update_scenes_with_video_urls, update_scenes_with_voiceover_urls,
    get_scenes_for_video, get_music_for_video, detect_video_workflow_type,
    update_video_id_for_scenes, update_video_id_for_music, update_scenes_with_revised_content
)
from .services.revision_ai import generate_revised_scenes_with_gpt4, generate_revised_wan_scenes_with_gpt4
from .services.task_utils import update_task_progress
from .services.wan_generation import generate_wan_scene_images_with_fal, generate_wan_voiceovers_with_fal, generate_wan_videos_with_fal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

# Configure fal client
if settings.fal_key:
    os.environ["FAL_KEY"] = settings.fal_key
    logger.info("WORKER: fal.ai client configured")
else:
    logger.warning("WORKER: FAL_KEY not found - fal.ai operations will fail")


async def process_video_request(ctx: Dict[str, Any], extracted_data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a video generation request through the complete pipeline"""
    try:
        logger.info("PIPELINE: Starting video processing pipeline...")
        
        # Convert dict back to ExtractedData model
        extracted_data = ExtractedData(**extracted_data_dict)
        logger.info(f"PIPELINE: Processing video: {extracted_data.video_id}")
        logger.info(f"PIPELINE: User: {extracted_data.user_email}")
        
        # Update task progress
        await update_task_progress(extracted_data.task_id, 5, "Starting video processing pipeline")
        
        # Step 1: Generate scenes using GPT-4
        logger.info("PIPELINE: Step 1 - Generating scenes with GPT-4...")
        await update_task_progress(extracted_data.task_id, 10, "Generating scenes with GPT-4")
        
        if not openai_client:
            error_msg = "OpenAI client not configured - missing OPENAI_API_KEY"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        scenes = await generate_scenes_with_gpt4(extracted_data.prompt, openai_client)
        if not scenes:
            error_msg = "Failed to generate scenes with GPT-4 - no scenes returned"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        logger.info(f"PIPELINE: Generated {len(scenes)} scenes successfully")
        
        # Step 2: Store scenes in database
        logger.info("PIPELINE: Step 2 - Storing scenes in database...")
        await update_task_progress(extracted_data.task_id, 15, "Storing scenes in database")
        
        scenes_stored = await store_scenes_in_supabase(scenes, extracted_data.video_id, extracted_data.user_id)
        if not scenes_stored:
            error_msg = "Failed to store scenes in database"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Step 3: Resize the initial product image
        logger.info("PIPELINE: Step 3 - Resizing initial product image...")
        await update_task_progress(extracted_data.task_id, 20, "Resizing product image")
        
        resized_image_url = await resize_image_with_fal(extracted_data.image_url, extracted_data.aspect_ratio)
        if not resized_image_url or resized_image_url == extracted_data.image_url:
            logger.warning("PIPELINE: Image resize failed or returned original image, continuing with original")
            resized_image_url = extracted_data.image_url
        logger.info(f"PIPELINE: Product image resized to {extracted_data.aspect_ratio}: {resized_image_url}")
        
        # Step 4: Generate scene images
        logger.info("PIPELINE: Step 4 - Generating scene images...")
        await update_task_progress(extracted_data.task_id, 25, "Generating scene images")
        
        # Extract image prompts from scenes
        image_prompts = [scene.get("image_prompt", "") for scene in scenes]
        scene_image_urls = await generate_scene_images_with_fal(image_prompts, resized_image_url)
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_images = len([url for url in scene_image_urls if url]) if scene_image_urls else 0
        if not scene_image_urls or len(scene_image_urls) != 5 or successful_images < 3:
            error_msg = f"Failed to generate scene images - got {len(scene_image_urls) if scene_image_urls else 0} total, {successful_images} successful (need at least 3 out of 5)"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with scene image URLs
        await update_scenes_with_image_urls(scene_image_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 5: Generate voiceovers
        logger.info("PIPELINE: Step 5 - Generating voiceovers...")
        await update_task_progress(extracted_data.task_id, 35, "Generating voiceovers")
        
        # Extract voiceover prompts from scenes
        voiceover_prompts = [scene.get("vioce_over", "") for scene in scenes]
        voiceover_urls = await generate_voiceovers_with_fal(voiceover_prompts)
        
        if voiceover_urls:
            await update_scenes_with_voiceover_urls(voiceover_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 6: Generate videos from scene images
        logger.info("PIPELINE: Step 6 - Generating videos from scene images...")
        await update_task_progress(extracted_data.task_id, 50, "Generating scene videos")
        
        # Extract visual descriptions from scenes
        video_prompts = [scene.get("visual_description", "") for scene in scenes]
        video_urls = await generate_videos_with_fal(scene_image_urls, video_prompts)
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_videos = len([url for url in video_urls if url]) if video_urls else 0
        if not video_urls or len(video_urls) != 5 or successful_videos < 3:
            error_msg = f"Failed to generate scene videos - got {len(video_urls) if video_urls else 0} total, {successful_videos} successful (need at least 3 out of 5)"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with scene video URLs
        await update_scenes_with_video_urls(video_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 7: Generate background music
        logger.info("PIPELINE: Step 7 - Generating background music...")
        await update_task_progress(extracted_data.task_id, 65, "Generating background music")
        
        # Extract music prompts from scenes
        music_prompts = [scene.get("music_direction", "") for scene in scenes]
        raw_music_url = await generate_background_music_with_fal(music_prompts)
        
        normalized_music_url = ""
        if raw_music_url:
            # Normalize music volume
            logger.info("PIPELINE: Normalizing background music volume...")
            normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
            
            # Store music in database
            await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
        
        # Step 8: Compose final video with all audio tracks
        logger.info("PIPELINE: Step 8 - Composing final video with audio...")
        await update_task_progress(extracted_data.task_id, 80, "Composing final video")
        
        # First compose video clips without audio
        from .services.video_generation import compose_final_video
        composed_video_url = await compose_final_video(video_urls)
        
        if not composed_video_url:
            error_msg = "Failed to compose final video - no video URL returned"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Then add all audio tracks
        final_video_url = await compose_final_video_with_audio(
            composed_video_url, 
            voiceover_urls, 
            normalized_music_url
        )
        
        if not final_video_url:
            final_video_url = composed_video_url  # Fallback to video without audio
        
        # Step 9: Add captions to final video
        logger.info("PIPELINE: Step 9 - Adding captions to final video...")
        await update_task_progress(extracted_data.task_id, 90, "Adding captions to final video")
        
        captioned_video_url = await add_captions_to_video(final_video_url)
        
        # Step 10: Send final video to frontend
        logger.info("PIPELINE: Step 10 - Sending final video to frontend...")
        await update_task_progress(extracted_data.task_id, 100, "Processing completed successfully")
        
        logger.info("PIPELINE: Sending final video to frontend...")
        callback_success = await send_video_callback(
            captioned_video_url,
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id,
            is_revision=False
        )
        
        if callback_success:
            logger.info("PIPELINE: Video processing completed successfully!")
        else:
            logger.warning("PIPELINE: Video processing completed but callback failed")
        
        return {
            "status": "completed",
            "final_video_url": captioned_video_url,
            "callback_sent": callback_success
        }
        
    except Exception as e:
        logger.error(f"PIPELINE: Video processing failed: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback
        await send_error_callback(
            str(e),
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id
        )
        
        return {
            "status": "failed",
            "error": str(e)
        }


async def process_wan_request(ctx: Dict[str, Any], extracted_data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a WAN video generation request through the complete pipeline"""
    try:
        logger.info("WAN_PIPELINE: Starting WAN video processing pipeline...")
        
        # Convert dict back to ExtractedWanData model
        extracted_data = ExtractedWanData(**extracted_data_dict)
        logger.info(f"WAN_PIPELINE: Processing WAN video: {extracted_data.video_id}")
        logger.info(f"WAN_PIPELINE: User: {extracted_data.user_email}")
        logger.info(f"WAN_PIPELINE: Model: {extracted_data.model}")
        
        # Update task progress
        await update_task_progress(extracted_data.task_id, 5, "Starting WAN video processing pipeline")
        
        # Step 1: Generate WAN scenes using GPT-4
        logger.info("WAN_PIPELINE: Step 1 - Generating WAN scenes with GPT-4...")
        await update_task_progress(extracted_data.task_id, 10, "Generating WAN scenes with GPT-4")
        
        if not openai_client:
            error_msg = "OpenAI client not configured - missing OPENAI_API_KEY"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        wan_scenes, music_prompt = await wan_scene_generator(extracted_data.prompt, openai_client)
        if not wan_scenes or len(wan_scenes) != 6:
            error_msg = f"Failed to generate WAN scenes with GPT-4 - got {len(wan_scenes) if wan_scenes else 0} instead of 6"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        logger.info(f"WAN_PIPELINE: Generated {len(wan_scenes)} WAN scenes successfully")
        if music_prompt:
            logger.info(f"WAN_PIPELINE: Music prompt extracted: {music_prompt[:100]}...")
        else:
            logger.warning("WAN_PIPELINE: No music prompt extracted from GPT-4 response")
            logger.warning("WAN_PIPELINE: This might be due to GPT-4 not following the new system prompt format")
        
        # Debug: Log the generated WAN scenes to see what GPT-4 created
        logger.info("WAN_PIPELINE: === GPT-4 Generated WAN Scenes ===")
        for i, scene in enumerate(wan_scenes, 1):
            logger.info(f"WAN_PIPELINE: Scene {i}:")
            logger.info(f"WAN_PIPELINE:   nano_banana_prompt: {scene.get('nano_banana_prompt', '')[:100]}...")
            logger.info(f"WAN_PIPELINE:   elevenlabs_prompt: {scene.get('elevenlabs_prompt', '')}")
            logger.info(f"WAN_PIPELINE:   wan2_5_prompt: {scene.get('wan2_5_prompt', '')[:100]}...")
        logger.info("WAN_PIPELINE: === End of GPT-4 Generated WAN Scenes ===")
        
        # Step 2: Store WAN scenes in database
        logger.info("WAN_PIPELINE: Step 2 - Storing WAN scenes in database...")
        await update_task_progress(extracted_data.task_id, 15, "Storing WAN scenes in database")
        
        scenes_stored = await store_wan_scenes_in_supabase(wan_scenes, extracted_data.video_id, extracted_data.user_id)
        if not scenes_stored:
            error_msg = "Failed to store WAN scenes in database"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Store the single music prompt separately in the music table
        if music_prompt and music_prompt.strip():
            logger.info("WAN_PIPELINE: Storing WAN music prompt in music table...")
            from .services.database_operations import store_wan_music_prompt_in_supabase
            await store_wan_music_prompt_in_supabase(music_prompt, extracted_data.video_id, extracted_data.user_id)
        
        # Step 3: Resize the initial product image
        logger.info("WAN_PIPELINE: Step 3 - Resizing initial product image...")
        await update_task_progress(extracted_data.task_id, 20, "Resizing product image for WAN")
        
        resized_image_url = await resize_image_with_fal(extracted_data.image_url, extracted_data.aspect_ratio)
        logger.info(f"WAN_PIPELINE: Product image resized to {extracted_data.aspect_ratio}: {resized_image_url}")
        
        # Step 4: Parallelize independent generation tasks (images, voiceovers, music)
        logger.info("WAN_PIPELINE: Step 4 - Starting parallel generation tasks...")
        await update_task_progress(extracted_data.task_id, 25, "Starting parallel generation (images, voiceovers, music)")
        
        # Extract nano_banana_prompts from WAN scenes
        nano_banana_prompts = [scene.get("nano_banana_prompt", "") for scene in wan_scenes]
        
        # Extract elevenlabs_prompts from WAN scenes
        
        # Create parallel tasks for independent generation steps
        logger.info("WAN_PIPELINE: Creating parallel tasks for images, voiceovers, and music...")
        
        # Task 1: Generate WAN scene images
        image_task = asyncio.create_task(
            generate_wan_scene_images_with_fal(nano_banana_prompts, resized_image_url)
        )
        logger.info("WAN_PIPELINE: Created image generation task")
        
        # Task 2: Generate WAN voiceovers (pass full scenes for emotion/voice_id support)
        voiceover_task = asyncio.create_task(
            generate_wan_voiceovers_with_fal(wan_scenes)
        )
        logger.info("WAN_PIPELINE: Created voiceover generation task")
        
        # Task 3: Generate background music (if music_prompt exists)
        music_task = None
        if music_prompt and music_prompt.strip():
            logger.info(f"WAN_PIPELINE: Creating music generation task with prompt: {music_prompt}")
            from .services.music_generation import generate_wan_background_music_with_fal
            music_task = asyncio.create_task(
                generate_wan_background_music_with_fal(music_prompt)
            )
        else:
            logger.warning("WAN_PIPELINE: No valid music prompt - creating default music task")
            default_music_prompt = "Lo-fi hip hop with calm steady beat"
            from .services.music_generation import generate_wan_background_music_with_fal
            music_task = asyncio.create_task(
                generate_wan_background_music_with_fal(default_music_prompt)
            )
        
        # Wait for all parallel tasks to complete
        logger.info("WAN_PIPELINE: Waiting for parallel tasks to complete...")
        await update_task_progress(extracted_data.task_id, 30, "Processing parallel generation tasks...")
        
        try:
            # Use asyncio.gather to run tasks concurrently
            scene_image_urls, voiceover_urls, raw_music_url = await asyncio.gather(
                image_task,
                voiceover_task,
                music_task,
                return_exceptions=True
            )
            
            # Handle any exceptions from parallel tasks
            if isinstance(scene_image_urls, Exception):
                logger.error(f"WAN_PIPELINE: Image generation task failed: {scene_image_urls}")
                scene_image_urls = []
            
            if isinstance(voiceover_urls, Exception):
                logger.error(f"WAN_PIPELINE: Voiceover generation task failed: {voiceover_urls}")
                voiceover_urls = []
            
            if isinstance(raw_music_url, Exception):
                logger.error(f"WAN_PIPELINE: Music generation task failed: {raw_music_url}")
                raw_music_url = ""
            
            logger.info("WAN_PIPELINE: All parallel tasks completed!")
            logger.info(f"WAN_PIPELINE: Generated {len([url for url in scene_image_urls if url])} scene images")
            logger.info(f"WAN_PIPELINE: Generated {len([url for url in voiceover_urls if url])} voiceovers")
            logger.info(f"WAN_PIPELINE: Music generation result: {'Success' if raw_music_url else 'Failed'}")
            
        except Exception as e:
            logger.error(f"WAN_PIPELINE: Error in parallel task execution: {e}")
            # Fallback to empty results
            scene_image_urls = []
            voiceover_urls = []
            raw_music_url = ""
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_images = len([url for url in scene_image_urls if url]) if scene_image_urls else 0
        if not scene_image_urls or len(scene_image_urls) != 6 or successful_images < 4:
            error_msg = f"Failed to generate WAN scene images - got {len(scene_image_urls) if scene_image_urls else 0} total, {successful_images} successful (need at least 4 out of 6)"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with WAN scene image URLs
        logger.info("WAN_PIPELINE: Updating database with scene image URLs...")
        await update_scenes_with_image_urls(scene_image_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Update database with voiceover URLs
        if voiceover_urls:
            logger.info("WAN_PIPELINE: Updating database with voiceover URLs...")
            await update_scenes_with_voiceover_urls(voiceover_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Check if enough voiceovers succeeded (allow some failures but not total failure)
        successful_voiceovers = len([url for url in voiceover_urls if url]) if voiceover_urls else 0
        if successful_voiceovers < 3:  # Need at least 3 out of 6 voiceovers
            error_msg = f"WAN voiceover generation failed - only {successful_voiceovers} out of 6 voiceovers generated successfully (need at least 3)"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Process background music (normalize and store)
        normalized_music_url = ""
        if raw_music_url:
            logger.info("WAN_PIPELINE: Normalizing background music volume...")
            normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
            
            # Update music record with actual generated music URL (replace the prompt placeholder)
            await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
            logger.info(f"WAN_PIPELINE: Background music processed and stored: {normalized_music_url}")
        else:
            logger.warning("WAN_PIPELINE: No background music generated")
        
        # Step 5: Generate WAN videos from scene images (depends on images, so runs after parallel tasks)
        logger.info("WAN_PIPELINE: Step 5 - Generating WAN videos from scene images...")
        await update_task_progress(extracted_data.task_id, 50, "Generating WAN scene videos")
        
        # Extract wan2_5_prompts from WAN scenes
        wan2_5_prompts = [scene.get("wan2_5_prompt", "") for scene in wan_scenes]
        video_urls = await generate_wan_videos_with_fal(scene_image_urls, wan2_5_prompts)
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_videos = len([url for url in video_urls if url]) if video_urls else 0
        if not video_urls or len(video_urls) != 6 or successful_videos < 4:
            error_msg = f"Failed to generate WAN scene videos - got {len(video_urls) if video_urls else 0} total, {successful_videos} successful (need at least 4 out of 6)"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with WAN scene video URLs
        await update_scenes_with_video_urls(video_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 6: Compose final WAN video using JSON2Video
        logger.info("WAN_PIPELINE: Step 6 - Composing WAN videos + voiceovers (JSON2Video Step 1)...")
        await update_task_progress(extracted_data.task_id, 75, "Composing videos with voiceovers")
        
        logger.info(f"WAN_PIPELINE: Step 1 - Passing {len(video_urls)} video URLs and {len(voiceover_urls)} voiceover URLs")
        logger.info(f"WAN_PIPELINE: Video URLs: {video_urls}")
        logger.info(f"WAN_PIPELINE: Voiceover URLs: {voiceover_urls}")
        logger.info(f"WAN_PIPELINE: Using aspect ratio: {extracted_data.aspect_ratio}")
        
        # Import the new JSON2Video functions
        from .services.json2video_composition import compose_wan_videos_and_voiceovers_with_json2video, compose_final_video_with_music_json2video
        
        # Step 1: Compose videos + voiceovers
        composed_video_url = await compose_wan_videos_and_voiceovers_with_json2video(video_urls, voiceover_urls, extracted_data.aspect_ratio)
        
        if not composed_video_url:
            error_msg = "Failed to compose WAN videos + voiceovers (Step 1) - no video URL returned"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        logger.info(f"WAN_PIPELINE: Step 1 completed - Composed video URL: {composed_video_url}")
        
        # Step 7: Compose final video with background music (JSON2Video Step 2)
        logger.info("WAN_PIPELINE: Step 7 - Adding background music to composed video (JSON2Video Step 2)...")
        await update_task_progress(extracted_data.task_id, 85, "Adding background music to final video")
        
        logger.info(f"WAN_PIPELINE: Step 2 - Adding background music: {normalized_music_url}")
        
        final_video_url = ""
        if normalized_music_url:
            # Step 2: Add background music to composed video
            final_video_url = await compose_final_video_with_music_json2video(composed_video_url, normalized_music_url, extracted_data.aspect_ratio)
        
        if not final_video_url:
            # Fallback to composed video without music if Step 2 fails
            logger.warning("WAN_PIPELINE: Step 2 failed or no music - using composed video without background music")
            final_video_url = composed_video_url
        
        logger.info(f"WAN_PIPELINE: Final video URL: {final_video_url}")
        
        # Step 8: Add captions to final WAN video
        logger.info("WAN_PIPELINE: Step 8 - Adding captions to final WAN video...")
        await update_task_progress(extracted_data.task_id, 90, "Adding captions to final WAN video")
        
        captioned_video_url = await add_captions_to_video(final_video_url, extracted_data.aspect_ratio)
        
        # Step 9: Send final WAN video to frontend
        logger.info("WAN_PIPELINE: Step 9 - Sending final WAN video to frontend...")
        await update_task_progress(extracted_data.task_id, 100, "WAN processing completed successfully")
        
        logger.info("WAN_PIPELINE: Sending final WAN video to frontend...")
        callback_success = await send_video_callback(
            captioned_video_url,
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id,
            is_revision=False
        )
        
        if callback_success:
            logger.info("WAN_PIPELINE: WAN video processing completed successfully!")
        else:
            logger.warning("WAN_PIPELINE: WAN video processing completed but callback failed")
        
        return {
            "status": "completed",
            "final_video_url": captioned_video_url,
            "callback_sent": callback_success
        }
        
    except Exception as e:
        logger.error(f"WAN_PIPELINE: WAN video processing failed: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback
        await send_error_callback(
            str(e),
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id
        )
        
        return {
            "status": "failed",
            "error": str(e)
        }


async def process_video_revision(ctx: Dict[str, Any], extracted_data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a video revision request"""
    try:
        logger.info("REVISION_PIPELINE: Starting video revision pipeline...")
        
        # Convert dict back to ExtractedRevisionData model
        extracted_data = ExtractedRevisionData(**extracted_data_dict)
        logger.info(f"REVISION_PIPELINE: Processing revision for video: {extracted_data.video_id}")
        logger.info(f"REVISION_PIPELINE: Parent video: {extracted_data.parent_video_id}")
        logger.info(f"REVISION_PIPELINE: User: {extracted_data.user_email}")
        logger.info(f"REVISION_PIPELINE: Revision request: {extracted_data.revision_request[:100]}...")
        
        # Update task progress
        await update_task_progress(extracted_data.task_id, 5, "Starting video revision pipeline")
        
        # Step 1: Get original scenes from database
        logger.info("REVISION_PIPELINE: Step 1 - Retrieving original scenes from database...")
        await update_task_progress(extracted_data.task_id, 10, "Retrieving original scenes")
        
        if not openai_client:
            error_msg = "OpenAI client not configured - missing OPENAI_API_KEY"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        # Detect workflow type (regular vs WAN)
        workflow_type = await detect_video_workflow_type(extracted_data.parent_video_id, extracted_data.user_id)
        logger.info(f"REVISION_PIPELINE: Detected workflow type: {workflow_type}")
        
        original_scenes = await get_scenes_for_video(extracted_data.parent_video_id, extracted_data.user_id)
        
        expected_scene_count = 6 if workflow_type == "wan" else 5
        if not original_scenes or len(original_scenes) != expected_scene_count:
            error_msg = f"Failed to retrieve original scenes - got {len(original_scenes) if original_scenes else 0} instead of {expected_scene_count}"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        logger.info(f"REVISION_PIPELINE: Retrieved {len(original_scenes)} original scenes")
        
        # Step 2: Generate revised scenes using appropriate GPT-4 function
        if workflow_type == "wan":
            logger.info("REVISION_PIPELINE: Step 2 - Generating revised WAN scenes with GPT-4...")
            await update_task_progress(extracted_data.task_id, 20, "Generating revised WAN scenes with GPT-4")
            
            revised_scenes, should_generate_music = await generate_revised_wan_scenes_with_gpt4(
                extracted_data.revision_request,
                original_scenes,
                openai_client
            )
            
            logger.info(f"REVISION_PIPELINE: Should generate new music: {should_generate_music}")
        else:
            logger.info("REVISION_PIPELINE: Step 2 - Generating revised regular scenes with GPT-4...")
            await update_task_progress(extracted_data.task_id, 20, "Generating revised scenes with GPT-4")
            
            revised_scenes = await generate_revised_scenes_with_gpt4(
                extracted_data.revision_request,
                original_scenes,
                openai_client
            )
            
            # For regular workflow, check if user mentions missing music
            revision_lower = extracted_data.revision_request.lower()
            music_missing_keywords = ["no music", "no background music", "missing music", "add music", "needs music", "without music", "no sound", "silent", "quiet", "muted"]
            should_generate_music = any(keyword in revision_lower for keyword in music_missing_keywords)
            logger.info(f"REVISION_PIPELINE: Should generate new music (regular): {should_generate_music}")
        
        if not revised_scenes or len(revised_scenes) != expected_scene_count:
            error_msg = f"Failed to generate revised scenes - got {len(revised_scenes) if revised_scenes else 0} instead of {expected_scene_count}"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        logger.info(f"REVISION_PIPELINE: Generated {len(revised_scenes)} revised scenes")
        
        # Step 3: Store revised scenes in database (create new scenes for revision video_id)
        logger.info("REVISION_PIPELINE: Step 3 - Storing revised scenes in database...")
        await update_task_progress(extracted_data.task_id, 25, "Storing revised scenes in database")
        
        # Use appropriate storage function based on workflow type
        if workflow_type == "wan":
            # For WAN revisions, we need to convert back to WAN format for storage
            wan_scenes_for_storage = []
            
            for scene in revised_scenes:
                wan_scene = {
                    "scene_number": scene.get("scene_number", 1),
                    "nano_banana_prompt": scene.get("image_prompt", ""),
                    "elevenlabs_prompt": scene.get("vioce_over", ""),
                    "wan2_5_prompt": scene.get("visual_description", "")
                }
                wan_scenes_for_storage.append(wan_scene)
            
            scenes_stored = await store_wan_scenes_in_supabase(wan_scenes_for_storage, extracted_data.video_id, extracted_data.user_id)
        else:
            scenes_stored = await store_scenes_in_supabase(revised_scenes, extracted_data.video_id, extracted_data.user_id)
            
        if not scenes_stored:
            error_msg = "Failed to store revised scenes in database"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        # Step 4: Resize the initial product image (use original image from revision data)
        logger.info("REVISION_PIPELINE: Step 4 - Resizing product image for revision...")
        await update_task_progress(extracted_data.task_id, 30, "Resizing product image")
        
        resized_image_url = await resize_image_with_fal(extracted_data.image_url, extracted_data.aspect_ratio)
        if not resized_image_url or resized_image_url == extracted_data.image_url:
            logger.warning("REVISION_PIPELINE: Image resize failed or returned original image, continuing with original")
            resized_image_url = extracted_data.image_url
        logger.info(f"REVISION_PIPELINE: Product image resized to {extracted_data.aspect_ratio}: {resized_image_url}")
        
        # Step 5: Generate scene images (only for changed scenes)
        logger.info("REVISION_PIPELINE: Step 5 - Generating scene images (granular regeneration)...")
        await update_task_progress(extracted_data.task_id, 40, "Generating revised scene images (selective)")
        
        final_scene_image_urls = []
        images_to_generate = []
        
        # Determine which images need regeneration
        for scene_change in scene_changes:
            if scene_change["image_needs_regen"]:
                images_to_generate.append({
                    "scene_number": scene_change["scene_number"],
                    "image_prompt": scene_change["revised_image_prompt"]
                })
                logger.info(f"REVISION_PIPELINE: Scene {scene_change['scene_number']} image will be regenerated")
            else:
                logger.info(f"REVISION_PIPELINE: Scene {scene_change['scene_number']} image will be reused: {scene_change['original_image_url']}")
        
        logger.info(f"REVISION_PIPELINE: Regenerating {len(images_to_generate)} out of {len(scene_changes)} scene images")
        
        # Generate only the images that need regeneration
        generated_images = {}
        if images_to_generate:
            if workflow_type == "wan":
                # For WAN, we need to generate all changed images at once
                image_prompts_to_generate = [img["image_prompt"] for img in images_to_generate]
                generated_image_urls = await generate_wan_scene_images_with_fal(image_prompts_to_generate, resized_image_url)
                
                # Map generated URLs back to scene numbers
                for i, img_info in enumerate(images_to_generate):
                    if i < len(generated_image_urls) and generated_image_urls[i]:
                        generated_images[img_info["scene_number"]] = generated_image_urls[i]
            else:
                # For regular workflow, generate images individually
                for img_info in images_to_generate:
                    try:
                        generated_url = await generate_single_scene_image_with_fal(
                            img_info["image_prompt"], 
                            resized_image_url
                        )
                        if generated_url:
                            generated_images[img_info["scene_number"]] = generated_url
                            logger.info(f"REVISION_PIPELINE: Generated new image for scene {img_info['scene_number']}")
                        else:
                            logger.warning(f"REVISION_PIPELINE: Failed to generate image for scene {img_info['scene_number']}")
                    except Exception as e:
                        logger.error(f"REVISION_PIPELINE: Error generating image for scene {img_info['scene_number']}: {e}")
        
        # Build final image URLs list (mix of generated and reused)
        for scene_change in scene_changes:
            scene_number = scene_change["scene_number"]
            if scene_number in generated_images:
                final_scene_image_urls.append(generated_images[scene_number])
            else:
                # Reuse original image
                final_scene_image_urls.append(scene_change["original_image_url"])
        
        # Validate we have enough successful images
        successful_images = len([url for url in final_scene_image_urls if url])
        min_required = 4 if workflow_type == "wan" else 3
        if successful_images < min_required:
            error_msg = f"Failed to get enough scene images - got {successful_images} successful (need at least {min_required} out of {expected_scene_count})"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        # Update database with final scene image URLs
        await update_scenes_with_image_urls(final_scene_image_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 6: Generate voiceovers (only for changed scenes)
        logger.info("REVISION_PIPELINE: Step 6 - Generating voiceovers (granular regeneration)...")
        await update_task_progress(extracted_data.task_id, 50, "Generating revised voiceovers (selective)")
        
        final_voiceover_urls = []
        
        # Check if any voiceovers need regeneration
        voiceovers_need_regen = any(sc["voiceover_needs_regen"] for sc in scene_changes)
        
        if voiceovers_need_regen:
            if workflow_type == "wan":
                # For WAN, if any voiceover changed, regenerate all (due to batch processing requirements)
                logger.info("REVISION_PIPELINE: WAN voiceover changes detected - regenerating all voiceovers")
                
                # Convert revised_scenes back to WAN format for voiceover generation
                wan_scenes_for_voiceover = []
                for scene in revised_scenes:
                    wan_scene = {
                        "scene_number": scene.get("scene_number", 1),
                        "elevenlabs_prompt": scene.get("vioce_over", ""),
                        "eleven_labs_emotion": "neutral",  # Default emotion
                        "eleven_labs_voice_id": "Friendly_Person"  # Default voice
                    }
                    wan_scenes_for_voiceover.append(wan_scene)
                
                voiceover_urls = await generate_wan_voiceovers_with_fal(wan_scenes_for_voiceover)
                final_voiceover_urls = voiceover_urls if voiceover_urls else [""] * expected_scene_count
            else:
                # For regular workflow, generate voiceovers individually for changed scenes
                logger.info("REVISION_PIPELINE: Generating individual voiceovers for changed scenes")
                
                for scene_change in scene_changes:
                    if scene_change["voiceover_needs_regen"]:
                        try:
                            generated_url = await generate_single_voiceover_with_fal(
                                scene_change["revised_voiceover_prompt"]
                            )
                            final_voiceover_urls.append(generated_url if generated_url else "")
                            if generated_url:
                                logger.info(f"REVISION_PIPELINE: Generated new voiceover for scene {scene_change['scene_number']}")
                            else:
                                logger.warning(f"REVISION_PIPELINE: Failed to generate voiceover for scene {scene_change['scene_number']}")
                        except Exception as e:
                            logger.error(f"REVISION_PIPELINE: Error generating voiceover for scene {scene_change['scene_number']}: {e}")
                            final_voiceover_urls.append("")
                    else:
                        # Reuse original voiceover
                        final_voiceover_urls.append(scene_change["original_voiceover_url"])
        else:
            # No voiceovers need regeneration - reuse all originals
            logger.info("REVISION_PIPELINE: No voiceover changes detected - reusing all original voiceovers")
            final_voiceover_urls = [sc["original_voiceover_url"] for sc in scene_changes]
        
        # Update database with final voiceover URLs
        if final_voiceover_urls:
            await update_scenes_with_voiceover_urls(final_voiceover_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 7: Generate videos (only for changed scenes)
        logger.info("REVISION_PIPELINE: Step 7 - Generating videos (granular regeneration)...")
        await update_task_progress(extracted_data.task_id, 65, "Generating revised scene videos (selective)")
        
        final_video_urls = []
        
        # Generate videos for scenes that need regeneration
        for i, scene_change in enumerate(scene_changes):
            if scene_change["video_needs_regen"]:
                try:
                    # Use the corresponding image URL from final_scene_image_urls
                    scene_image_url = final_scene_image_urls[i] if i < len(final_scene_image_urls) else ""
                    
                    if not scene_image_url:
                        logger.warning(f"REVISION_PIPELINE: No image URL available for scene {scene_change['scene_number']} video generation")
                        final_video_urls.append("")
                        continue
                    
                    generated_url = await generate_single_video_with_fal(
                        scene_image_url,
                        scene_change["revised_video_prompt"]
                    )
                    final_video_urls.append(generated_url if generated_url else "")
                    if generated_url:
                        logger.info(f"REVISION_PIPELINE: Generated new video for scene {scene_change['scene_number']}")
                    else:
                        logger.warning(f"REVISION_PIPELINE: Failed to generate video for scene {scene_change['scene_number']}")
                except Exception as e:
                    logger.error(f"REVISION_PIPELINE: Error generating video for scene {scene_change['scene_number']}: {e}")
                    final_video_urls.append("")
            else:
                # Reuse original video
                final_video_urls.append(scene_change["original_video_url"])
                logger.info(f"REVISION_PIPELINE: Reusing original video for scene {scene_change['scene_number']}")
        
        # Validate we have enough successful videos
        successful_videos = len([url for url in final_video_urls if url])
        min_required_videos = 4 if workflow_type == "wan" else 3
        if successful_videos < min_required_videos:
            error_msg = f"Failed to get enough scene videos - got {successful_videos} successful (need at least {min_required_videos} out of {expected_scene_count})"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        # Update database with final video URLs
        await update_scenes_with_video_urls(final_video_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Log regeneration summary
        images_regenerated = sum(1 for sc in scene_changes if sc["image_needs_regen"])
        voiceovers_regenerated = len([url for i, url in enumerate(final_voiceover_urls) if scene_changes[i]["voiceover_needs_regen"] and url])
        videos_regenerated = sum(1 for sc in scene_changes if sc["video_needs_regen"])
        
        logger.info(f"REVISION_PIPELINE: Granular regeneration completed:")
        logger.info(f"REVISION_PIPELINE: - Images regenerated: {images_regenerated}/{expected_scene_count}")
        logger.info(f"REVISION_PIPELINE: - Voiceovers regenerated: {voiceovers_regenerated}/{expected_scene_count}")
        logger.info(f"REVISION_PIPELINE: - Videos regenerated: {videos_regenerated}/{expected_scene_count}")
        
        # Step 8: Get or generate background music (try to reuse from parent video first)
        logger.info("REVISION_PIPELINE: Step 8 - Getting background music...")
        await update_task_progress(extracted_data.task_id, 75, "Getting background music")
        
        # Try to get existing music from parent video (unless user specifically mentions missing music)
        existing_music = await get_music_for_video(extracted_data.parent_video_id, extracted_data.user_id)
        normalized_music_url = ""
        
        if existing_music and existing_music.get("music_url") and not should_generate_music:
            # Reuse existing music from parent video
            normalized_music_url = existing_music["music_url"]
            logger.info(f"REVISION_PIPELINE: Reusing music from parent video: {normalized_music_url[:100]}...")
            
            # Store music for revision video
            await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
        else:
            # Generate new music if parent doesn't have any OR user specifically mentioned missing music
            if should_generate_music:
                logger.info("REVISION_PIPELINE: User mentioned missing music - generating new background music...")
            else:
                logger.info("REVISION_PIPELINE: No existing music found, generating new background music...")
                
            # For WAN revisions, we don't have music_direction field, so use a default
            if workflow_type == "wan":
                from .services.music_generation import generate_wan_background_music_with_fal
                default_music_prompt = "Lo-fi hip hop with calm steady beat"
                raw_music_url = await generate_wan_background_music_with_fal(default_music_prompt)
            else:
                music_prompts = [scene.get("music_direction", "") for scene in revised_scenes]
                raw_music_url = await generate_background_music_with_fal(music_prompts)
            
            if raw_music_url:
                # Normalize music volume
                logger.info("REVISION_PIPELINE: Normalizing background music volume...")
                normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
                
                # Store music in database
                await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
            else:
                logger.warning("REVISION_PIPELINE: Failed to generate new background music - proceeding without music")
        
        # Step 9: Compose final revision video with all audio tracks
        logger.info("REVISION_PIPELINE: Step 9 - Composing final revision video with audio...")
        await update_task_progress(extracted_data.task_id, 85, "Composing final revision video")
        
        # Use appropriate composition function based on workflow type
        if workflow_type == "wan":
            # For WAN revisions, use JSON2Video composition
            from .services.json2video_composition import compose_wan_videos_and_voiceovers_with_json2video, compose_final_video_with_music_json2video
            
            # Step 1: Compose videos + voiceovers
            composed_video_url = await compose_wan_videos_and_voiceovers_with_json2video(final_video_urls, final_voiceover_urls, extracted_data.aspect_ratio)
            
            if not composed_video_url:
                error_msg = "Failed to compose final WAN revision video - no video URL returned"
                logger.error(f"REVISION_PIPELINE: {error_msg}")
                await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
                raise Exception(error_msg)
            
            # Step 2: Add background music if available
            final_video_url = composed_video_url
            if normalized_music_url:
                final_video_url = await compose_final_video_with_music_json2video(composed_video_url, normalized_music_url, extracted_data.aspect_ratio)
                if not final_video_url:
                    final_video_url = composed_video_url  # Fallback to video without music
        else:
            # For regular revisions, use fal.ai composition
            from .services.video_generation import compose_final_video
            composed_video_url = await compose_final_video(final_video_urls)
            
            if not composed_video_url:
                error_msg = "Failed to compose final revision video - no video URL returned"
                logger.error(f"REVISION_PIPELINE: {error_msg}")
                await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
                raise Exception(error_msg)
            
            # Then add all audio tracks
            final_video_url = await compose_final_video_with_audio(
                composed_video_url, 
                final_voiceover_urls, 
                normalized_music_url
            )
            
            if not final_video_url:
                final_video_url = composed_video_url  # Fallback to video without audio
        
        # Step 10: Add captions to final revision video
        logger.info("REVISION_PIPELINE: Step 10 - Adding captions to final revision video...")
        await update_task_progress(extracted_data.task_id, 95, "Adding captions to final revision video")
        
        captioned_video_url = await add_captions_to_video(final_video_url, extracted_data.aspect_ratio)
        
        # Step 11: Send final revision video to frontend
        logger.info("REVISION_PIPELINE: Step 11 - Sending final revision video to frontend...")
        await update_task_progress(extracted_data.task_id, 100, "Revision processing completed successfully")
        
        logger.info("REVISION_PIPELINE: Sending final revision video to frontend...")
        callback_success = await send_video_callback(
            captioned_video_url,
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id,
            is_revision=True
        )
        
        if callback_success:
            logger.info("REVISION_PIPELINE: Video revision processing completed successfully!")
        else:
            logger.warning("REVISION_PIPELINE: Video revision processing completed but callback failed")
        
        return {
            "status": "completed",
            "final_video_url": captioned_video_url,
            "callback_sent": callback_success
        }
        
    except Exception as e:
        logger.error(f"REVISION_PIPELINE: Video revision processing failed: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback
        await send_error_callback(
            str(e),
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id
        )
        
        return {
            "status": "failed",
            "error": str(e)
        }


# ARQ Worker Settings
class WorkerSettings:
    """ARQ Worker configuration settings"""
    
    # Redis connection settings
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    
    # Worker configuration
    functions = [
        process_video_request,
        process_wan_request,
        process_video_revision,
    ]
    
    # Job settings
    job_timeout = settings.task_timeout  # Use timeout from settings (15 minutes)
    max_jobs = settings.max_concurrent_tasks  # Use max concurrent tasks from settings
    max_tries = 3  # Retry failed jobs up to 3 times
    
    # Health check settings
    health_check_interval = 30  # Check worker health every 30 seconds
    
    # Logging
    log_results = True
    
    # Keep job results for debugging
    keep_result = 3600  # Keep results for 1 hour


# Export WorkerSettings for use by run_worker.py
__all__ = ['WorkerSettings']
