import asyncio
import logging
from typing import List, Dict, Optional
import httpx
from ..config import get_settings
from .task_utils import get_resolution_from_aspect_ratio
from .ffmpeg_api_client import submit_merge_task, submit_background_music_task
from .polling_service import poll_merge_task, poll_background_music_task

logger = logging.getLogger(__name__)
settings = get_settings()


async def compose_final_video_with_audio(
    composed_video_url: str,
    voiceover_urls: List[str],
    normalized_music_url: str,
    aspect_ratio: str = "9:16"
) -> str:
    """
    Compose the final video with background music using FFmpeg API.
    Note: This is a simplified version since FFmpeg API handles music addition only.
    Voiceovers should be merged with videos in a separate step.
    """
    try:
        logger.info("COMPOSE_FFMPEG: Starting final video composition with background music...")
        logger.info(f"COMPOSE_FFMPEG: Main video URL: {composed_video_url}")
        logger.info(f"COMPOSE_FFMPEG: Background music URL: {normalized_music_url}")
        logger.info(f"COMPOSE_FFMPEG: Note - Voiceovers should already be merged with video")

        # If no music URL, return the composed video as-is
        if not normalized_music_url:
            logger.warning("COMPOSE_FFMPEG: No background music URL provided, returning video as-is")
            return composed_video_url

        # Submit background music task to FFmpeg API
        logger.info("COMPOSE_FFMPEG: Submitting background music task...")

        task_id = await submit_background_music_task(
            video_url=composed_video_url,
            music_url=normalized_music_url,
            music_volume=0.3,  # Low volume for background music
            video_volume=1.0   # Full volume for video (already has voiceovers)
        )

        if not task_id:
            logger.error("COMPOSE_FFMPEG: Failed to submit background music task, returning original video")
            return composed_video_url

        logger.info(f"COMPOSE_FFMPEG: Background music task submitted - Task ID: {task_id}")
        logger.info("COMPOSE_FFMPEG: Starting immediate polling...")

        # Poll for completion (immediate start, 5-second intervals)
        final_video_url = await poll_background_music_task(task_id, max_wait_time=300)  # 5 minutes

        if final_video_url:
            logger.info(f"COMPOSE_FFMPEG: Success! URL: {final_video_url}")
            return final_video_url
        else:
            logger.error("COMPOSE_FFMPEG: Composition failed or timed out, returning original video")
            return composed_video_url

    except Exception as e:
        logger.error(f"COMPOSE_FFMPEG: Failed: {e}")
        logger.exception("Full traceback:")
        return composed_video_url


async def compose_wan_final_video_with_audio(
    scene_clip_urls: List[str],
    voiceover_urls: List[str],
    aspect_ratio: str = "9:16"
) -> str:
    """
    Compose the final WAN video with all audio tracks using FFmpeg API:
    - 6 scene videos (5 seconds each = 30 seconds total)
    - 6 voiceovers (aligned with their respective scenes)
    """
    try:
        logger.info("WAN_COMPOSE_FFMPEG: Starting WAN final video composition...")
        logger.info(f"WAN_COMPOSE_FFMPEG: Scene clips: {len(scene_clip_urls)} videos")
        logger.info(f"WAN_COMPOSE_FFMPEG: Voiceovers: {len(voiceover_urls)} voiceovers")

        # Debug: Log all voiceover URLs
        for i, voiceover_url in enumerate(voiceover_urls):
            if voiceover_url:
                logger.info(f"WAN_COMPOSE_FFMPEG: Voiceover {i+1}: {voiceover_url}")
            else:
                logger.warning(f"WAN_COMPOSE_FFMPEG: Voiceover {i+1} is empty")

        # Filter out empty URLs
        valid_scene_clips = [url for url in scene_clip_urls if url]

        logger.info(f"WAN_COMPOSE_FFMPEG: Valid clips: {len(valid_scene_clips)}/{len(scene_clip_urls)}")
        logger.info(f"WAN_COMPOSE_FFMPEG: Valid voiceovers: {len([v for v in voiceover_urls if v])}/{len(voiceover_urls)}")

        if len([v for v in voiceover_urls if v]) == 0:
            logger.error("WAN_COMPOSE_FFMPEG: No valid voiceovers!")
            logger.error(f"WAN_COMPOSE_FFMPEG: Voiceover URLs: {voiceover_urls}")

        if not valid_scene_clips:
            logger.error("WAN_COMPOSE_FFMPEG: No valid scene clips")
            return ""

        # Get resolution
        width, height = get_resolution_from_aspect_ratio(aspect_ratio)
        logger.info(f"WAN_COMPOSE_FFMPEG: Using resolution {width}x{height}")

        # Submit merge task to FFmpeg API
        logger.info("WAN_COMPOSE_FFMPEG: Submitting merge task...")

        task_id = await submit_merge_task(
            scene_clip_urls=valid_scene_clips,
            voiceover_urls=voiceover_urls[:len(valid_scene_clips)],  # Match voiceover count to scene count
            width=width,
            height=height,
            video_volume=0.2,  # Low volume for scene video
            voiceover_volume=2.0  # High volume for voiceover
        )

        if not task_id:
            logger.error("WAN_COMPOSE_FFMPEG: Failed to submit merge task")
            return ""

        logger.info(f"WAN_COMPOSE_FFMPEG: Merge task submitted - Task ID: {task_id}")
        logger.info("WAN_COMPOSE_FFMPEG: Starting immediate polling...")

        # Poll for completion (immediate start, 5-second intervals)
        final_video_url = await poll_merge_task(task_id, max_wait_time=480)  # 8 minutes

        if final_video_url:
            logger.info(f"WAN_COMPOSE_FFMPEG: Success! URL: {final_video_url}")
            return final_video_url
        else:
            logger.error("WAN_COMPOSE_FFMPEG: Composition failed or timed out")
            return ""

    except Exception as e:
        logger.error(f"WAN_COMPOSE_FFMPEG: Failed: {e}")
        logger.exception("Full traceback:")
        return ""
