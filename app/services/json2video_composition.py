import asyncio
import logging
import httpx
from typing import List, Optional
from ..config import get_settings
from .task_utils import get_resolution_from_aspect_ratio
from .ffmpeg_api_client import submit_merge_task, submit_background_music_task
from .polling_service import poll_merge_task, poll_background_music_task

logger = logging.getLogger(__name__)
settings = get_settings()


async def compose_wan_videos_and_voiceovers_with_ffmpeg(
    scene_clip_urls: List[str],
    voiceover_urls: List[str],
    aspect_ratio: str = "9:16"
) -> Optional[str]:
    """
    First step: Compose WAN videos with voiceovers using FFmpeg API (6 scenes)

    Args:
        scene_clip_urls: List of 6 scene video URLs
        voiceover_urls: List of 6 voiceover audio URLs

    Returns:
        Composed video URL (videos + voiceovers) if successful, None if failed
    """
    try:
        logger.info("FFMPEG_COMPOSE: Starting WAN videos + voiceovers composition (Step 1)...")
        logger.info(f"FFMPEG_COMPOSE: Scene clips: {len(scene_clip_urls)} videos")
        logger.info(f"FFMPEG_COMPOSE: Voiceovers: {len(voiceover_urls)} voiceovers")

        # Keep original arrays to maintain scene index correspondence
        valid_scene_clips = [url for url in scene_clip_urls if url]

        logger.info(f"FFMPEG_COMPOSE: Valid scene clips: {len(valid_scene_clips)} out of {len(scene_clip_urls)}")
        logger.info(f"FFMPEG_COMPOSE: Processing {len(voiceover_urls)} voiceover URLs (some may be empty)")

        if len(valid_scene_clips) < 4:  # Need at least 4 scenes
            logger.error(f"FFMPEG_COMPOSE: Not enough valid scene clips: {len(valid_scene_clips)} (need at least 4)")
            return None

        # Get dynamic resolution based on aspect ratio
        width, height = get_resolution_from_aspect_ratio(aspect_ratio)
        logger.info(f"FFMPEG_COMPOSE: Using resolution {width}x{height} for aspect ratio {aspect_ratio}")

        # Submit merge task to FFmpeg API
        logger.info("FFMPEG_COMPOSE: Submitting merge task to FFmpeg API...")

        task_id = await submit_merge_task(
            scene_clip_urls=valid_scene_clips,
            voiceover_urls=voiceover_urls[:len(valid_scene_clips)],  # Match voiceover count to scene count
            width=width,
            height=height,
            video_volume=0.2,  # Low volume for scene video
            voiceover_volume=2.0  # High volume for voiceover
        )

        if not task_id:
            logger.error("FFMPEG_COMPOSE: Failed to submit merge task")
            return None

        logger.info(f"FFMPEG_COMPOSE: Merge task submitted - Task ID: {task_id}")
        logger.info("FFMPEG_COMPOSE: Starting immediate polling...")

        # Poll for completion (immediate start, 5-second intervals)
        composed_video_url = await poll_merge_task(task_id, max_wait_time=480)  # 8 minutes

        if composed_video_url:
            logger.info("FFMPEG_COMPOSE: Step 1 composition (videos + voiceovers) completed successfully!")
            logger.info(f"FFMPEG_COMPOSE: Step 1 composed video URL: {composed_video_url}")
            return composed_video_url
        else:
            logger.error("FFMPEG_COMPOSE: Step 1 composition failed or timed out")
            return None

    except Exception as e:
        logger.error(f"FFMPEG_COMPOSE: Failed to compose Step 1 (videos + voiceovers): {e}")
        logger.exception("Full traceback:")
        return None


async def compose_final_video_with_music_ffmpeg(
    composed_video_url: str,
    music_url: str,
    aspect_ratio: str = "9:16"
) -> Optional[str]:
    """
    Second step: Compose the already composed video (videos + voiceovers) with background music using FFmpeg API

    Args:
        composed_video_url: The composed video from Step 1 (videos + voiceovers)
        music_url: Background music URL

    Returns:
        Final video URL with music if successful, None if failed
    """
    try:
        logger.info("FFMPEG_MUSIC: Starting Step 2 composition (composed video + music)...")
        logger.info(f"FFMPEG_MUSIC: Composed video URL: {composed_video_url}")
        logger.info(f"FFMPEG_MUSIC: Background music URL: {music_url}")

        if not composed_video_url or not music_url:
            logger.error("FFMPEG_MUSIC: Missing composed video URL or music URL for Step 2")
            return None

        # Submit background music task to FFmpeg API
        logger.info("FFMPEG_MUSIC: Submitting background music task to FFmpeg API...")

        task_id = await submit_background_music_task(
            video_url=composed_video_url,
            music_url=music_url,
            music_volume=0.3,  # Low volume for background music
            video_volume=1.0   # Full volume for video (already has voiceovers)
        )

        if not task_id:
            logger.error("FFMPEG_MUSIC: Failed to submit background music task")
            return None

        logger.info(f"FFMPEG_MUSIC: Background music task submitted - Task ID: {task_id}")
        logger.info("FFMPEG_MUSIC: Starting immediate polling...")

        # Poll for completion (immediate start, 5-second intervals)
        final_video_url = await poll_background_music_task(task_id, max_wait_time=300)  # 5 minutes

        if final_video_url:
            logger.info("FFMPEG_MUSIC: Step 2 composition (composed video + music) completed successfully!")
            logger.info(f"FFMPEG_MUSIC: Final video URL with music: {final_video_url}")
            return final_video_url
        else:
            logger.error("FFMPEG_MUSIC: Step 2 composition failed or timed out")
            return None

    except Exception as e:
        logger.error(f"FFMPEG_MUSIC: Failed to compose Step 2 (composed video + music): {e}")
        logger.exception("Full traceback:")
        return None


async def check_json2video_status(project_id: str, max_wait_time: int = 600) -> Optional[str]:
    """
    Poll JSON2Video API until the composition job is complete
    
    Args:
        project_id: The project ID from the composition request
        max_wait_time: Maximum time to wait in seconds (default: 10 minutes)
        
    Returns:
        Final video URL if successful, None if failed
    """
    try:
        logger.info(f"JSON2VIDEO: Checking status for project: {project_id}")
        logger.info(f"JSON2VIDEO: Maximum wait time: {max_wait_time} seconds")
        
        if not settings.json2video_api_key:
            logger.error("JSON2VIDEO: JSON2VIDEO_API_KEY not found")
            return None
        
        headers = {"x-api-key": settings.json2video_api_key}
        start_time = asyncio.get_event_loop().time()
        interval = 10  # Check every 10 seconds
        check_count = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                check_count += 1
                
                # Check if we've exceeded max wait time
                elapsed_time = asyncio.get_event_loop().time() - start_time
                if elapsed_time > max_wait_time:
                    logger.error(f"JSON2VIDEO: Timeout after {max_wait_time} seconds ({check_count} checks)")
                    return None
                
                try:
                    logger.info(f"JSON2VIDEO: Status check #{check_count} (elapsed: {elapsed_time:.1f}s)")
                    
                    response = await client.get(
                        f"https://api.json2video.com/v2/movies?project={project_id}",
                        headers=headers
                    )
                    
                    logger.info(f"JSON2VIDEO: Status API response: {response.status_code}")
                    
                    if response.status_code != 200:
                        logger.error(f"JSON2VIDEO: Status API returned {response.status_code}: {response.text}")
                        await asyncio.sleep(interval)
                        continue
                    
                    data = response.json()
                    logger.info(f"JSON2VIDEO: Status response data: {data}")
                    
                    movie = data.get("movie", {})
                    status = movie.get("status", "unknown")
                    message = movie.get("message", "")
                    progress = movie.get("progress", 0)
                    
                    logger.info(f"JSON2VIDEO: Status [{status}] Progress: {progress}% - {message}")
                    
                    if status == "done":
                        video_url = movie.get("url")
                        duration = movie.get("duration")
                        
                        if video_url:
                            logger.info("JSON2VIDEO: Composition completed successfully!")
                            logger.info(f"JSON2VIDEO: Final video URL: {video_url}")
                            if duration:
                                logger.info(f"JSON2VIDEO: Video duration: {duration}s")
                            return video_url
                        else:
                            logger.error(f"JSON2VIDEO: No video URL in completed response: {movie}")
                            return None
                            
                    elif status == "error":
                        error_details = movie.get("error", message)
                        logger.error(f"JSON2VIDEO: Composition error: {error_details}")
                        logger.error(f"JSON2VIDEO: Full error response: {movie}")
                        return None
                        
                    elif status in ["pending", "running"]:
                        logger.info(f"JSON2VIDEO: Still processing... ({status}) - {progress}%")
                        await asyncio.sleep(interval)
                        continue
                        
                    else:
                        logger.warning(f"JSON2VIDEO: Unknown status: {status} - {message}")
                        logger.warning(f"JSON2VIDEO: Full response: {movie}")
                        await asyncio.sleep(interval)
                        continue
                        
                except httpx.HTTPError as e:
                    logger.error(f"JSON2VIDEO: HTTP error checking status (attempt {check_count}): {e}")
                    await asyncio.sleep(interval)
                    continue
                except Exception as e:
                    logger.error(f"JSON2VIDEO: Unexpected error checking status (attempt {check_count}): {e}")
                    await asyncio.sleep(interval)
                    continue
                    
    except Exception as e:
        logger.error(f"JSON2VIDEO: Failed to check composition status: {e}")
        logger.exception("Full traceback:")
        return None
