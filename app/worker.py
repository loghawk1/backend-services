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
    get_scenes_for_video, get_music_for_video,
    update_video_id_for_scenes, update_video_id_for_music, update_scenes_with_revised_content
)
from .services.revision_ai import generate_revised_scenes_with_gpt4
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
        
        resized_image_url = await resize_image_with_fal(extracted_data.image_url)
        if not resized_image_url or resized_image_url == extracted_data.image_url:
            logger.warning("PIPELINE: Image resize failed or returned original image, continuing with original")
            resized_image_url = extracted_data.image_url
        logger.info(f"PIPELINE: Product image resized: {resized_image_url}")
        
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
            extracted_data.user_id,
            is_revision=False
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
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, extracted_data.callback_url, is_revision=False)
            raise Exception(error_msg)
        
        wan_scenes, music_prompt = await wan_scene_generator(extracted_data.prompt, openai_client)
        if not wan_scenes or len(wan_scenes) != 6:
            error_msg = f"Failed to generate WAN scenes with GPT-4 - got {len(wan_scenes) if wan_scenes else 0} instead of 6"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, extracted_data.callback_url, is_revision=False)
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
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, extracted_data.callback_url, is_revision=False)
            raise Exception(error_msg)
        
        # Step 3: Resize the initial product image
        logger.info("WAN_PIPELINE: Step 3 - Resizing initial product image...")
        await update_task_progress(extracted_data.task_id, 20, "Resizing product image for WAN")
        
        resized_image_url = await resize_image_with_fal(extracted_data.image_url)
        logger.info(f"WAN_PIPELINE: Product image resized: {resized_image_url}")
        
        # Step 4: Generate WAN scene images using Gemini edit
        logger.info("WAN_PIPELINE: Step 4 - Generating WAN scene images...")
        await update_task_progress(extracted_data.task_id, 25, "Generating WAN scene images with Gemini edit")
        
        # Extract nano_banana_prompts from WAN scenes
        nano_banana_prompts = [scene.get("nano_banana_prompt", "") for scene in wan_scenes]
        scene_image_urls = await generate_wan_scene_images_with_fal(nano_banana_prompts, resized_image_url)
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_images = len([url for url in scene_image_urls if url]) if scene_image_urls else 0
        if not scene_image_urls or len(scene_image_urls) != 6 or successful_images < 4:
            error_msg = f"Failed to generate WAN scene images - got {len(scene_image_urls) if scene_image_urls else 0} total, {successful_images} successful (need at least 4 out of 6)"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with WAN scene image URLs
        await update_scenes_with_image_urls(scene_image_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 5: Generate WAN voiceovers
        logger.info("WAN_PIPELINE: Step 5 - Generating WAN voiceovers...")
        await update_task_progress(extracted_data.task_id, 35, "Generating WAN voiceovers")
        
        # Extract elevenlabs_prompts from WAN scenes
        elevenlabs_prompts = [scene.get("elevenlabs_prompt", "") for scene in wan_scenes]
        logger.info(f"WAN_PIPELINE: Extracted {len(elevenlabs_prompts)} elevenlabs prompts")
        for i, prompt in enumerate(elevenlabs_prompts):
            logger.info(f"WAN_PIPELINE: ElevenLabs prompt {i+1}: {prompt[:100]}...")
        
        voiceover_urls = await generate_wan_voiceovers_with_fal(elevenlabs_prompts)
        logger.info(f"WAN_PIPELINE: Generated voiceover URLs: {voiceover_urls}")
        
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
        
        # Step 6: Generate WAN videos from scene images
        logger.info("WAN_PIPELINE: Step 6 - Generating WAN videos from scene images...")
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
        
        # Step 7: Generate background music from music_prompt
        logger.info("WAN_PIPELINE: Step 7 - Generating background music from music_prompt...")
        await update_task_progress(extracted_data.task_id, 65, "Generating background music")
        
        normalized_music_url = ""
        if music_prompt:
            logger.info(f"WAN_PIPELINE: Using music prompt: {music_prompt}")
            raw_music_url = await generate_wan_background_music_with_fal(music_prompt)
            
            if raw_music_url:
                # Normalize music volume
                logger.info("WAN_PIPELINE: Normalizing background music volume...")
                normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
                
                # Store music in database
                await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
                logger.info(f"WAN_PIPELINE: Background music generated and stored: {normalized_music_url}")
            else:
                logger.error("WAN_PIPELINE: Failed to generate background music from Lyria")
        else:
            logger.warning("WAN_PIPELINE: No music prompt provided - this indicates GPT-4 didn't return music_prompt")
            logger.warning("WAN_PIPELINE: Skipping music generation")
        
        # Step 8: Compose final WAN video using JSON2Video
        logger.info("WAN_PIPELINE: Step 8 - Composing WAN videos + voiceovers (JSON2Video Step 1)...")
        await update_task_progress(extracted_data.task_id, 75, "Composing videos with voiceovers")
        
        logger.info(f"WAN_PIPELINE: Step 1 - Passing {len(video_urls)} video URLs and {len(voiceover_urls)} voiceover URLs")
        logger.info(f"WAN_PIPELINE: Video URLs: {video_urls}")
        logger.info(f"WAN_PIPELINE: Voiceover URLs: {voiceover_urls}")
        
        # Import the new JSON2Video functions
        from .services.json2video_composition import compose_wan_videos_and_voiceovers_with_json2video, compose_final_video_with_music_json2video
        
        # Step 1: Compose videos + voiceovers
        composed_video_url = await compose_wan_videos_and_voiceovers_with_json2video(video_urls, voiceover_urls)
        
        if not composed_video_url:
            error_msg = "Failed to compose WAN videos + voiceovers (Step 1) - no video URL returned"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        logger.info(f"WAN_PIPELINE: Step 1 completed - Composed video URL: {composed_video_url}")
        
        # Step 9: Compose final video with background music (JSON2Video Step 2)
        logger.info("WAN_PIPELINE: Step 9 - Adding background music to composed video (JSON2Video Step 2)...")
        await update_task_progress(extracted_data.task_id, 85, "Adding background music to final video")
        
        logger.info(f"WAN_PIPELINE: Step 2 - Adding background music: {normalized_music_url}")
        
        final_video_url = ""
        if normalized_music_url:
            # Step 2: Add background music to composed video
            final_video_url = await compose_final_video_with_music_json2video(composed_video_url, normalized_music_url)
        
        if not final_video_url:
            # Fallback to composed video without music if Step 2 fails
            logger.warning("WAN_PIPELINE: Step 2 failed or no music - using composed video without background music")
            final_video_url = composed_video_url
        
        logger.info(f"WAN_PIPELINE: Final video URL: {final_video_url}")
        
        # Step 10: Send final WAN video to frontend (skip captions since JSON2Video handles them)
        logger.info("WAN_PIPELINE: Step 10 - Sending final WAN video to frontend...")
        await update_task_progress(extracted_data.task_id, 100, "WAN processing completed successfully")
        
        logger.info("WAN_PIPELINE: Sending final WAN video to frontend...")
        callback_success = await send_video_callback(
            final_video_url,  # JSON2Video already handles captions
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
            "final_video_url": final_video_url,
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
            extracted_data.user_id,
            is_revision=False
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
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, extracted_data.callback_url, is_revision=True)
            raise Exception(error_msg)
        
        original_scenes = await get_scenes_for_video(extracted_data.parent_video_id, extracted_data.user_id)
        if not original_scenes or len(original_scenes) != 5:
            error_msg = f"Failed to retrieve original scenes - got {len(original_scenes) if original_scenes else 0} instead of 5"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, extracted_data.
