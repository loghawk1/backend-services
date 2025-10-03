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
from .services.image_processing import generate_scene_images_with_fal
from .services.audio_generation import generate_voiceovers_with_fal
from .services.video_generation import generate_videos_with_fal
from .services.music_generation import generate_background_music_with_fal, normalize_music_volume, store_music_in_database
from .services.final_composition import compose_final_video_with_audio, compose_wan_final_video_with_audio
from .services.caption_generation import add_captions_to_video
from .services.callback_service import send_video_callback, send_error_callback
from .services.revision_ai import compare_scenes_for_changes
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
        
        # Step 3: Generate scene images (using original image with aspect ratio)
        logger.info("PIPELINE: Step 3 - Generating scene images...")
        await update_task_progress(extracted_data.task_id, 25, "Generating scene images")
        
        # Extract image prompts from scenes
        image_prompts = [scene.get("image_prompt", "") for scene in scenes]
        scene_image_urls = await generate_scene_images_with_fal(image_prompts, extracted_data.image_url, extracted_data.aspect_ratio)
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_images = len([url for url in scene_image_urls if url]) if scene_image_urls else 0
        if not scene_image_urls or len(scene_image_urls) != 5 or successful_images < 3:
            error_msg = f"Failed to generate scene images - got {len(scene_image_urls) if scene_image_urls else 0} total, {successful_images} successful (need at least 3 out of 5)"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with scene image URLs
        await update_scenes_with_image_urls(scene_image_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 4: Generate voiceovers
        logger.info("PIPELINE: Step 4 - Generating voiceovers...")
        await update_task_progress(extracted_data.task_id, 35, "Generating voiceovers")
        
        # Extract voiceover prompts from scenes
        voiceover_prompts = [scene.get("vioce_over", "") for scene in scenes]
        voiceover_urls = await generate_voiceovers_with_fal(voiceover_prompts)
        
        if voiceover_urls:
            await update_scenes_with_voiceover_urls(voiceover_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 5: Generate videos from scene images
        logger.info("PIPELINE: Step 5 - Generating videos from scene images...")
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
        
        # Step 6: Generate background music
        logger.info("PIPELINE: Step 6 - Generating background music...")
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
        
        # Step 7: Compose final video with audio
        logger.info("PIPELINE: Step 7 - Composing final video with all audio tracks...")
        await update_task_progress(extracted_data.task_id, 80, "Composing final video with audio")
        
        # First compose videos without audio
        from .services.video_generation import compose_final_video
        composed_video_url = await compose_final_video(video_urls)
        
        if not composed_video_url:
            error_msg = "Failed to compose final video from scene videos"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Then add all audio tracks
        final_video_url = await compose_final_video_with_audio(
            composed_video_url,
            voiceover_urls,
            normalized_music_url,
            extracted_data.aspect_ratio
        )
        
        if not final_video_url:
            error_msg = "Failed to compose final video with audio tracks"
            logger.error(f"PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Step 8: Add captions to video
        logger.info("PIPELINE: Step 8 - Adding captions to video...")
        await update_task_progress(extracted_data.task_id, 90, "Adding captions to video")
        
        captioned_video_url = await add_captions_to_video(final_video_url, extracted_data.aspect_ratio)
        
        # Step 9: Send callback with final video
        logger.info("PIPELINE: Step 9 - Sending callback with final video...")
        await update_task_progress(extracted_data.task_id, 95, "Sending callback with final video")
        
        callback_success = await send_video_callback(
            captioned_video_url,
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id,
            extracted_data.callback_url,
            is_revision=False
        )
        
        if callback_success:
            logger.info("PIPELINE: Video processing completed successfully!")
            await update_task_progress(extracted_data.task_id, 100, "Video processing completed successfully")
            return {
                "status": "completed",
                "final_video_url": captioned_video_url,
                "video_id": extracted_data.video_id
            }
        else:
            logger.error("PIPELINE: Callback failed but video was processed successfully")
            return {
                "status": "completed_callback_failed",
                "final_video_url": captioned_video_url,
                "video_id": extracted_data.video_id
            }
        
    except Exception as e:
        logger.error(f"PIPELINE: Video processing failed: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback
        try:
            await send_error_callback(
                str(e),
                extracted_data.video_id,
                extracted_data.chat_id,
                extracted_data.user_id,
                extracted_data.callback_url,
                is_revision=False
            )
        except Exception as callback_error:
            logger.error(f"PIPELINE: Failed to send error callback: {callback_error}")
        
        return {
            "status": "failed",
            "error": str(e),
            "video_id": extracted_data.video_id
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
        if not wan_scenes:
            error_msg = "Failed to generate WAN scenes with GPT-4 - no scenes returned"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        logger.info(f"WAN_PIPELINE: Generated {len(wan_scenes)} WAN scenes successfully")
        logger.info(f"WAN_PIPELINE: Music prompt extracted: {music_prompt[:50]}...")
        
        # Debug: Log all WAN scenes generated by GPT-4
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
        
        # Store WAN music prompt in music table
        logger.info("WAN_PIPELINE: Storing WAN music prompt in music table...")
        from .services.database_operations import store_wan_music_prompt_in_supabase
        await store_wan_music_prompt_in_supabase(music_prompt, extracted_data.video_id, extracted_data.user_id)
        
        # Step 3: Generate WAN scene images (using original image with aspect ratio)
        logger.info("WAN_PIPELINE: Step 3 - Generating WAN scene images...")
        await update_task_progress(extracted_data.task_id, 25, "Generating WAN scene images")
        
        # Extract nano_banana_prompts from WAN scenes
        nano_banana_prompts = [scene.get("nano_banana_prompt", "") for scene in wan_scenes]
        scene_image_urls = await generate_wan_scene_images_with_fal(nano_banana_prompts, extracted_data.image_url, extracted_data.aspect_ratio)
        
        # Check if we got the right number of results AND if enough scenes succeeded
        successful_images = len([url for url in scene_image_urls if url]) if scene_image_urls else 0
        if not scene_image_urls or len(scene_image_urls) != 6 or successful_images < 4:
            error_msg = f"Failed to generate WAN scene images - got {len(scene_image_urls) if scene_image_urls else 0} total, {successful_images} successful (need at least 4 out of 6)"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Update database with scene image URLs
        await update_scenes_with_image_urls(scene_image_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 4: Generate WAN voiceovers
        logger.info("WAN_PIPELINE: Step 4 - Generating WAN voiceovers...")
        await update_task_progress(extracted_data.task_id, 35, "Generating WAN voiceovers")
        
        voiceover_urls = await generate_wan_voiceovers_with_fal(wan_scenes)
        
        if voiceover_urls:
            await update_scenes_with_voiceover_urls(voiceover_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 5: Generate WAN videos from scene images
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
        
        # Update database with scene video URLs
        await update_scenes_with_video_urls(video_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 6: Generate WAN background music
        logger.info("WAN_PIPELINE: Step 6 - Generating WAN background music...")
        await update_task_progress(extracted_data.task_id, 65, "Generating WAN background music")
        
        from .services.music_generation import generate_wan_background_music_with_fal
        raw_music_url = await generate_wan_background_music_with_fal(music_prompt)
        
        normalized_music_url = ""
        if raw_music_url:
            # Normalize music volume
            logger.info("WAN_PIPELINE: Normalizing WAN background music volume...")
            normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
            
            # Store music in database
            await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
        
        # Step 7: Compose final WAN video with audio
        logger.info("WAN_PIPELINE: Step 7 - Composing final WAN video with all audio tracks...")
        await update_task_progress(extracted_data.task_id, 80, "Composing final WAN video with audio")
        
        # For WAN, we compose videos + voiceovers directly (no separate composition step)
        final_video_url = await compose_wan_final_video_with_audio(
            video_urls,
            voiceover_urls,
            extracted_data.aspect_ratio
        )
        
        if not final_video_url:
            error_msg = "Failed to compose final WAN video with audio tracks"
            logger.error(f"WAN_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=False)
            raise Exception(error_msg)
        
        # Step 8: Add background music to the composed video
        if normalized_music_url:
            logger.info("WAN_PIPELINE: Step 8 - Adding background music to WAN video...")
            await update_task_progress(extracted_data.task_id, 85, "Adding background music to WAN video")
            
            from .services.json2video_composition import compose_final_video_with_music_json2video
            final_video_with_music = await compose_final_video_with_music_json2video(
                final_video_url, 
                normalized_music_url, 
                extracted_data.aspect_ratio
            )
            
            if final_video_with_music:
                final_video_url = final_video_with_music
                logger.info("WAN_PIPELINE: Background music added successfully")
            else:
                logger.warning("WAN_PIPELINE: Failed to add background music, continuing without it")
        
        # Step 9: Add captions to WAN video
        logger.info("WAN_PIPELINE: Step 9 - Adding captions to WAN video...")
        await update_task_progress(extracted_data.task_id, 90, "Adding captions to WAN video")
        
        captioned_video_url = await add_captions_to_video(final_video_url, extracted_data.aspect_ratio)
        
        # Step 10: Send callback with final WAN video
        logger.info("WAN_PIPELINE: Step 10 - Sending callback with final WAN video...")
        await update_task_progress(extracted_data.task_id, 95, "Sending callback with final WAN video")
        
        callback_success = await send_video_callback(
            captioned_video_url,
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id,
            extracted_data.callback_url,
            is_revision=False
        )
        
        if callback_success:
            logger.info("WAN_PIPELINE: WAN video processing completed successfully!")
            await update_task_progress(extracted_data.task_id, 100, "WAN video processing completed successfully")
            return {
                "status": "completed",
                "final_video_url": captioned_video_url,
                "video_id": extracted_data.video_id,
                "model": "wan"
            }
        else:
            logger.error("WAN_PIPELINE: Callback failed but WAN video was processed successfully")
            return {
                "status": "completed_callback_failed",
                "final_video_url": captioned_video_url,
                "video_id": extracted_data.video_id,
                "model": "wan"
            }
        
    except Exception as e:
        logger.error(f"WAN_PIPELINE: WAN video processing failed: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback
        try:
            await send_error_callback(
                str(e),
                extracted_data.video_id,
                extracted_data.chat_id,
                extracted_data.user_id,
                extracted_data.callback_url,
                is_revision=False
            )
        except Exception as callback_error:
            logger.error(f"WAN_PIPELINE: Failed to send error callback: {callback_error}")
        
        return {
            "status": "failed",
            "error": str(e),
            "video_id": extracted_data.video_id,
            "model": "wan"
        }


async def process_video_revision(ctx: Dict[str, Any], extracted_data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a video revision request through the complete pipeline"""
    try:
        logger.info("REVISION_PIPELINE: Starting video revision processing pipeline...")
        
        # Convert dict back to ExtractedRevisionData model
        extracted_data = ExtractedRevisionData(**extracted_data_dict)
        logger.info(f"REVISION_PIPELINE: Processing revision for video: {extracted_data.video_id}")
        logger.info(f"REVISION_PIPELINE: Parent video: {extracted_data.parent_video_id}")
        logger.info(f"REVISION_PIPELINE: User: {extracted_data.user_email}")
        logger.info(f"REVISION_PIPELINE: Revision request: {extracted_data.revision_request[:100]}...")
        
        # Update task progress
        await update_task_progress(extracted_data.task_id, 5, "Starting video revision processing pipeline")
        
        # Step 1: Detect workflow type (regular vs WAN)
        logger.info("REVISION_PIPELINE: Step 1 - Detecting workflow type...")
        await update_task_progress(extracted_data.task_id, 10, "Detecting workflow type")
        
        workflow_type = await detect_video_workflow_type(extracted_data.parent_video_id, extracted_data.user_id)
        logger.info(f"REVISION_PIPELINE: Detected workflow type: {workflow_type}")
        
        # Step 2: Get original scenes from database
        logger.info("REVISION_PIPELINE: Step 2 - Retrieving original scenes from database...")
        await update_task_progress(extracted_data.task_id, 15, "Retrieving original scenes")
        
        original_scenes = await get_scenes_for_video(extracted_data.parent_video_id, extracted_data.user_id)
        if not original_scenes:
            error_msg = f"No original scenes found for parent video: {extracted_data.parent_video_id}"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        logger.info(f"REVISION_PIPELINE: Retrieved {len(original_scenes)} original scenes")
        
        # Step 3: Generate revised scenes using AI
        logger.info("REVISION_PIPELINE: Step 3 - Generating revised scenes with AI...")
        await update_task_progress(extracted_data.task_id, 20, "Generating revised scenes with AI")
        
        if not openai_client:
            error_msg = "OpenAI client not configured - missing OPENAI_API_KEY"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        if workflow_type == "wan":
            # Use WAN revision AI
            result = await generate_revised_wan_scenes_with_gpt4(
                extracted_data.revision_request, 
                original_scenes, 
                openai_client
            )
            
            # Handle both scenes and music generation flag
            if isinstance(result, tuple) and len(result) == 2:
                revised_scenes, should_generate_music = result
            else:
                revised_scenes = result
                should_generate_music = False
                
            logger.info(f"REVISION_PIPELINE: WAN revision - should generate music: {should_generate_music}")
        else:
            # Use regular revision AI
            revised_scenes = await generate_revised_scenes_with_gpt4(
                extracted_data.revision_request, 
                original_scenes, 
                openai_client
            )
            should_generate_music = False
        
        if not revised_scenes:
            error_msg = "Failed to generate revised scenes with AI"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        logger.info(f"REVISION_PIPELINE: Generated {len(revised_scenes)} revised scenes")
        
        # Step 4: Compare scenes to determine what needs regeneration
        logger.info("REVISION_PIPELINE: Step 4 - Comparing scenes for granular regeneration...")
        await update_task_progress(extracted_data.task_id, 25, "Analyzing changes for granular regeneration")
        
        scene_changes = await compare_scenes_for_changes(original_scenes, revised_scenes)
        if not scene_changes:
            error_msg = "Failed to compare scenes for changes"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        # Step 5: Update database with revised scene content
        logger.info("REVISION_PIPELINE: Step 5 - Updating database with revised content...")
        await update_task_progress(extracted_data.task_id, 30, "Updating database with revised content")
        
        # First, update the video_id for all scenes and music to the new revision video_id
        await update_video_id_for_scenes(extracted_data.parent_video_id, extracted_data.video_id, extracted_data.user_id)
        await update_video_id_for_music(extracted_data.parent_video_id, extracted_data.video_id, extracted_data.user_id)
        
        # Then update with revised content
        await update_scenes_with_revised_content(revised_scenes, extracted_data.video_id, extracted_data.user_id)
        
        # Step 6: Regenerate only changed assets
        logger.info("REVISION_PIPELINE: Step 6 - Regenerating changed assets...")
        
        # Regenerate images for changed scenes
        images_to_regenerate = [sc for sc in scene_changes if sc["image_needs_regen"]]
        if images_to_regenerate:
            logger.info(f"REVISION_PIPELINE: Regenerating {len(images_to_regenerate)} scene images...")
            await update_task_progress(extracted_data.task_id, 35, f"Regenerating {len(images_to_regenerate)} scene images")
            
            for scene_change in images_to_regenerate:
                scene_number = scene_change["scene_number"]
                revised_image_prompt = scene_change["revised_image_prompt"]
                
                logger.info(f"REVISION_PIPELINE: Regenerating image for scene {scene_number}...")
                
                from .services.single_asset_generation import generate_single_scene_image_with_fal
                new_image_url = await generate_single_scene_image_with_fal(
                    revised_image_prompt, 
                    extracted_data.image_url, 
                    extracted_data.aspect_ratio
                )
                
                if new_image_url:
                    # Update the scene_change with the new image URL
                    scene_change["new_image_url"] = new_image_url
                    logger.info(f"REVISION_PIPELINE: Scene {scene_number} image regenerated successfully")
                else:
                    logger.warning(f"REVISION_PIPELINE: Failed to regenerate image for scene {scene_number}, keeping original")
                    scene_change["new_image_url"] = scene_change["original_image_url"]
        
        # Regenerate voiceovers for changed scenes
        voiceovers_to_regenerate = [sc for sc in scene_changes if sc["voiceover_needs_regen"]]
        if voiceovers_to_regenerate:
            logger.info(f"REVISION_PIPELINE: Regenerating {len(voiceovers_to_regenerate)} voiceovers...")
            await update_task_progress(extracted_data.task_id, 45, f"Regenerating {len(voiceovers_to_regenerate)} voiceovers")
            
            for scene_change in voiceovers_to_regenerate:
                scene_number = scene_change["scene_number"]
                
                if workflow_type == "wan":
                    # For WAN, create a scene dict with the revised voiceover data
                    wan_scene_data = {
                        "elevenlabs_prompt": scene_change["revised_voiceover_prompt"],
                        "eleven_labs_emotion": scene_change["revised_emotion"],
                        "eleven_labs_voice_id": scene_change["revised_voice_id"]
                    }
                    
                    logger.info(f"REVISION_PIPELINE: Regenerating WAN voiceover for scene {scene_number}...")
                    logger.info(f"REVISION_PIPELINE: Voice: {wan_scene_data['eleven_labs_voice_id']}, Emotion: {wan_scene_data['eleven_labs_emotion']}")
                    
                    new_voiceover_urls = await generate_wan_voiceovers_with_fal([wan_scene_data])
                    new_voiceover_url = new_voiceover_urls[0] if new_voiceover_urls and new_voiceover_urls[0] else ""
                else:
                    # For regular workflow
                    revised_voiceover_prompt = scene_change["revised_voiceover_prompt"]
                    
                    logger.info(f"REVISION_PIPELINE: Regenerating voiceover for scene {scene_number}...")
                    
                    from .services.single_asset_generation import generate_single_voiceover_with_fal
                    new_voiceover_url = await generate_single_voiceover_with_fal(revised_voiceover_prompt)
                
                if new_voiceover_url:
                    # Update the scene_change with the new voiceover URL
                    scene_change["new_voiceover_url"] = new_voiceover_url
                    logger.info(f"REVISION_PIPELINE: Scene {scene_number} voiceover regenerated successfully")
                else:
                    logger.warning(f"REVISION_PIPELINE: Failed to regenerate voiceover for scene {scene_number}, keeping original")
                    scene_change["new_voiceover_url"] = scene_change["original_voiceover_url"]
        
        # Regenerate videos for changed scenes
        videos_to_regenerate = [sc for sc in scene_changes if sc["video_needs_regen"]]
        if videos_to_regenerate:
            logger.info(f"REVISION_PIPELINE: Regenerating {len(videos_to_regenerate)} scene videos...")
            await update_task_progress(extracted_data.task_id, 55, f"Regenerating {len(videos_to_regenerate)} scene videos")
            
            for scene_change in videos_to_regenerate:
                scene_number = scene_change["scene_number"]
                revised_video_prompt = scene_change["revised_video_prompt"]
                
                # Use the new image URL if it was regenerated, otherwise use original
                image_url = scene_change.get("new_image_url", scene_change["original_image_url"])
                
                logger.info(f"REVISION_PIPELINE: Regenerating video for scene {scene_number}...")
                
                from .services.single_asset_generation import generate_single_video_with_fal
                new_video_url = await generate_single_video_with_fal(image_url, revised_video_prompt)
                
                if new_video_url:
                    # Update the scene_change with the new video URL
                    scene_change["new_video_url"] = new_video_url
                    logger.info(f"REVISION_PIPELINE: Scene {scene_number} video regenerated successfully")
                else:
                    logger.warning(f"REVISION_PIPELINE: Failed to regenerate video for scene {scene_number}, keeping original")
                    scene_change["new_video_url"] = scene_change["original_video_url"]
        
        # Step 7: Update database with new asset URLs
        logger.info("REVISION_PIPELINE: Step 7 - Updating database with new asset URLs...")
        await update_task_progress(extracted_data.task_id, 65, "Updating database with new asset URLs")
        
        # Collect all final URLs (new or original)
        final_image_urls = []
        final_voiceover_urls = []
        final_video_urls = []
        
        for scene_change in scene_changes:
            final_image_urls.append(scene_change.get("new_image_url", scene_change["original_image_url"]))
            final_voiceover_urls.append(scene_change.get("new_voiceover_url", scene_change["original_voiceover_url"]))
            final_video_urls.append(scene_change.get("new_video_url", scene_change["original_video_url"]))
        
        # Update database with final URLs
        await update_scenes_with_image_urls(final_image_urls, extracted_data.video_id, extracted_data.user_id)
        await update_scenes_with_voiceover_urls(final_voiceover_urls, extracted_data.video_id, extracted_data.user_id)
        await update_scenes_with_video_urls(final_video_urls, extracted_data.video_id, extracted_data.user_id)
        
        # Step 8: Generate new music if needed (WAN workflow only)
        if workflow_type == "wan" and should_generate_music:
            logger.info("REVISION_PIPELINE: Step 8 - Generating new background music for WAN revision...")
            await update_task_progress(extracted_data.task_id, 70, "Generating new background music")
            
            # Use default music prompt for missing music
            default_music_prompt = "Lo-fi hip-hop with a light upbeat rhythm, soft percussion, and a steady background flow. Casual and positive, perfect for maintaining a smooth ad vibe across all scenes, ending gently at the final call-to-action."
            
            from .services.music_generation import generate_wan_background_music_with_fal
            raw_music_url = await generate_wan_background_music_with_fal(default_music_prompt)
            
            if raw_music_url:
                # Normalize music volume
                logger.info("REVISION_PIPELINE: Normalizing new background music volume...")
                normalized_music_url = await normalize_music_volume(raw_music_url, offset=-15.0)
                
                # Store music in database
                await store_music_in_database(normalized_music_url, extracted_data.video_id, extracted_data.user_id)
                logger.info("REVISION_PIPELINE: New background music generated and stored successfully")
            else:
                logger.warning("REVISION_PIPELINE: Failed to generate new background music")
        
        # Step 9: Get existing music for composition
        logger.info("REVISION_PIPELINE: Step 9 - Retrieving music for composition...")
        music_record = await get_music_for_video(extracted_data.video_id, extracted_data.user_id)
        normalized_music_url = music_record.get("music_url", "") if music_record else ""
        
        # Step 10: Compose final revision video
        logger.info("REVISION_PIPELINE: Step 10 - Composing final revision video...")
        await update_task_progress(extracted_data.task_id, 75, "Composing final revision video")
        
        if workflow_type == "wan":
            # WAN composition
            final_video_url = await compose_wan_final_video_with_audio(
                final_video_urls,
                final_voiceover_urls,
                extracted_data.aspect_ratio
            )
            
            # Add background music if available
            if normalized_music_url and final_video_url:
                logger.info("REVISION_PIPELINE: Adding background music to WAN revision video...")
                
                from .services.json2video_composition import compose_final_video_with_music_json2video
                final_video_with_music = await compose_final_video_with_music_json2video(
                    final_video_url, 
                    normalized_music_url, 
                    extracted_data.aspect_ratio
                )
                
                if final_video_with_music:
                    final_video_url = final_video_with_music
                    logger.info("REVISION_PIPELINE: Background music added to WAN revision successfully")
        else:
            # Regular composition
            from .services.video_generation import compose_final_video
            composed_video_url = await compose_final_video(final_video_urls)
            
            if composed_video_url:
                final_video_url = await compose_final_video_with_audio(
                    composed_video_url,
                    final_voiceover_urls,
                    normalized_music_url,
                    extracted_data.aspect_ratio
                )
            else:
                final_video_url = ""
        
        if not final_video_url:
            error_msg = "Failed to compose final revision video"
            logger.error(f"REVISION_PIPELINE: {error_msg}")
            await send_error_callback(error_msg, extracted_data.video_id, extracted_data.chat_id, extracted_data.user_id, is_revision=True)
            raise Exception(error_msg)
        
        # Step 11: Add captions to revision video
        logger.info("REVISION_PIPELINE: Step 11 - Adding captions to revision video...")
        await update_task_progress(extracted_data.task_id, 85, "Adding captions to revision video")
        
        captioned_video_url = await add_captions_to_video(final_video_url, extracted_data.aspect_ratio)
        
        # Step 12: Send callback with final revision video
        logger.info("REVISION_PIPELINE: Step 12 - Sending callback with final revision video...")
        await update_task_progress(extracted_data.task_id, 95, "Sending callback with final revision video")
        
        callback_success = await send_video_callback(
            captioned_video_url,
            extracted_data.video_id,
            extracted_data.chat_id,
            extracted_data.user_id,
            extracted_data.callback_url,
            is_revision=True
        )
        
        if callback_success:
            logger.info("REVISION_PIPELINE: Video revision processing completed successfully!")
            await update_task_progress(extracted_data.task_id, 100, "Video revision processing completed successfully")
            return {
                "status": "completed",
                "final_video_url": captioned_video_url,
                "video_id": extracted_data.video_id,
                "parent_video_id": extracted_data.parent_video_id,
                "workflow_type": workflow_type
            }
        else:
            logger.error("REVISION_PIPELINE: Callback failed but revision video was processed successfully")
            return {
                "status": "completed_callback_failed",
                "final_video_url": captioned_video_url,
                "video_id": extracted_data.video_id,
                "parent_video_id": extracted_data.parent_video_id,
                "workflow_type": workflow_type
            }
        
    except Exception as e:
        logger.error(f"REVISION_PIPELINE: Video revision processing failed: {e}")
        logger.exception("Full traceback:")
        
        # Send error callback
        try:
            await send_error_callback(
                str(e),
                extracted_data.video_id,
                extracted_data.chat_id,
                extracted_data.user_id,
                extracted_data.callback_url,
                is_revision=True
            )
        except Exception as callback_error:
            logger.error(f"REVISION_PIPELINE: Failed to send error callback: {callback_error}")
        
        return {
            "status": "failed",
            "error": str(e),
            "video_id": extracted_data.video_id,
            "parent_video_id": extracted_data.parent_video_id
        }


# ARQ Worker Settings
class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_video_request, process_wan_request, process_video_revision]
    job_timeout = settings.task_timeout
    max_jobs = settings.max_concurrent_tasks
    max_tries = 3
    keep_result = 3600  # Keep results for 1 hour
