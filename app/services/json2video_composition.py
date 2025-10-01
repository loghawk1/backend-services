import asyncio
import logging
import httpx
from typing import List, Optional
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def compose_wan_videos_and_voiceovers_with_json2video(
    scene_clip_urls: List[str], 
    voiceover_urls: List[str]
) -> Optional[str]:
    """
    First step: Compose WAN videos with voiceovers using JSON2Video API (6 scenes)
    
    Args:
        scene_clip_urls: List of 6 scene video URLs
        voiceover_urls: List of 6 voiceover audio URLs  
        
    Returns:
        Composed video URL (videos + voiceovers) if successful, None if failed
    """
    try:
        logger.info("JSON2VIDEO: Starting WAN videos + voiceovers composition (Step 1)...")
        logger.info(f"JSON2VIDEO: Scene clips: {len(scene_clip_urls)} videos")
        logger.info(f"JSON2VIDEO: Voiceovers: {len(voiceover_urls)} voiceovers")
        
        if not settings.json2video_api_key:
            logger.error("JSON2VIDEO: JSON2VIDEO_API_KEY not found in environment variables")
            return None
        
        # Filter out empty URLs
        valid_scene_clips = [url for url in scene_clip_urls if url]
        valid_voiceovers = [url for url in voiceover_urls if url]
        
        logger.info(f"JSON2VIDEO: Valid scene clips: {len(valid_scene_clips)} out of {len(scene_clip_urls)}")
        logger.info(f"JSON2VIDEO: Valid voiceovers: {len(valid_voiceovers)} out of {len(voiceover_urls)}")
        
        if len(valid_scene_clips) < 4:  # Need at least 4 scenes
            logger.error(f"JSON2VIDEO: Not enough valid scene clips: {len(valid_scene_clips)} (need at least 4)")
            return None
        
        # Build scenes array for JSON2Video (Step 1: Videos + Voiceovers only)
        scenes = []
        
        for i in range(min(6, len(valid_scene_clips))):  # Process up to 6 scenes
            scene_elements = []
            
            # Add video element
            if i < len(valid_scene_clips) and valid_scene_clips[i]:
                video_element = {
                    "type": "video",
                    "src": valid_scene_clips[i],
                    "duration": 5,  # 5 seconds per scene
                    "volume": 0.2,  # Low volume for scene video
                    "resize": "cover"
                }
                scene_elements.append(video_element)
                logger.info(f"JSON2VIDEO: Added video for scene {i+1}: {valid_scene_clips[i]}")
            
            # Add voiceover element if available
            if i < len(valid_voiceovers) and valid_voiceovers[i]:
                voiceover_element = {
                    "type": "audio",
                    "src": valid_voiceovers[i],
                    "start": 0,
                    "duration": 5,  # 5 seconds per voiceover
                    "volume": 2  # High volume for voiceover
                }
                scene_elements.append(voiceover_element)
                logger.info(f"JSON2VIDEO: Added voiceover for scene {i+1}: {valid_voiceovers[i]}")
            
            if scene_elements:
                scenes.append({"elements": scene_elements})
        
        logger.info(f"JSON2VIDEO: Created {len(scenes)} scenes for Step 1 composition (videos + voiceovers)")
        
        # Prepare JSON2Video payload for Step 1
        json_data = {
            "resolution": "custom", # 9:16 aspect ratio
            "width": 1080,
            "height": 1920,
            "scenes": scenes
        }
        
        logger.info("JSON2VIDEO: Sending Step 1 composition request (videos + voiceovers)...")
        logger.info(f"JSON2VIDEO: Payload scenes count: {len(json_data['scenes'])}")
        
        # Send composition request
        headers = {
            "x-api-key": settings.json2video_api_key,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.json2video.com/v2/movies",
                json=json_data,
                headers=headers
            )
        
        logger.info(f"JSON2VIDEO: Step 1 composition request response: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"JSON2VIDEO: Step 1 composition request failed with status {response.status_code}")
            logger.error(f"JSON2VIDEO: Response content: {response.text}")
            return None
        
        response_data = response.json()
        
        if not response_data.get("success"):
            logger.error(f"JSON2VIDEO: Step 1 composition request returned success=false: {response_data}")
            return None
        
        project_id = response_data.get("project")
        if not project_id:
            logger.error(f"JSON2VIDEO: No project ID in Step 1 response: {response_data}")
            return None
        
        logger.info(f"JSON2VIDEO: Step 1 composition started with project ID: {project_id}")
        
        # Poll for completion
        composed_video_url = await check_json2video_status(project_id, max_wait_time=600)  # 10 minutes
        
        if composed_video_url:
            logger.info("JSON2VIDEO: Step 1 composition (videos + voiceovers) completed successfully!")
            logger.info(f"JSON2VIDEO: Step 1 composed video URL: {composed_video_url}")
            return composed_video_url
        else:
            logger.error("JSON2VIDEO: Step 1 composition failed or timed out")
            return None
        
    except Exception as e:
        logger.error(f"JSON2VIDEO: Failed to compose Step 1 (videos + voiceovers): {e}")
        logger.exception("Full traceback:")
        return None


async def compose_final_video_with_music_json2video(
    composed_video_url: str,
    music_url: str
) -> Optional[str]:
    """
    Second step: Compose the already composed video (videos + voiceovers) with background music
    
    Args:
        composed_video_url: The composed video from Step 1 (videos + voiceovers)
        music_url: Background music URL
        
    Returns:
        Final video URL with music if successful, None if failed
    """
    try:
        logger.info("JSON2VIDEO: Starting Step 2 composition (composed video + music)...")
        logger.info(f"JSON2VIDEO: Composed video URL: {composed_video_url}")
        logger.info(f"JSON2VIDEO: Background music URL: {music_url}")
        
        if not settings.json2video_api_key:
            logger.error("JSON2VIDEO: JSON2VIDEO_API_KEY not found in environment variables")
            return None
        
        if not composed_video_url or not music_url:
            logger.error("JSON2VIDEO: Missing composed video URL or music URL for Step 2")
            return None
        
        # Build single scene with composed video + background music
        scene_elements = [
            {
                "type": "video",
                "src": composed_video_url,
                "start": 0,
                "duration": 30,  # 30 seconds total (6 scenes × 5 seconds)
                "volume": 0.5,  # Full volume for composed video (already has videos + voiceovers)
                "resize": "cover"
            },
            {
                "type": "audio",
                "src": music_url,
                "start": 0,
                "duration": 30,  # 30 seconds background music
                "volume": 1  # Low volume for background music
            }
        ]
        
        # Prepare JSON2Video payload for Step 2
        json_data = {
            "resolution": "custom", # 9:16 aspect ratio
            "width": 1080,
            "height": 1920,
            "scenes": [{"elements": scene_elements}]
        }
        
        logger.info("JSON2VIDEO: Sending Step 2 composition request (composed video + music)...")
        
        # Send composition request
        headers = {
            "x-api-key": settings.json2video_api_key,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.json2video.com/v2/movies",
                json=json_data,
                headers=headers
            )
        
        logger.info(f"JSON2VIDEO: Step 2 composition request response: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"JSON2VIDEO: Step 2 composition request failed with status {response.status_code}")
            logger.error(f"JSON2VIDEO: Response content: {response.text}")
            return None
        
        response_data = response.json()
        
        if not response_data.get("success"):
            logger.error(f"JSON2VIDEO: Step 2 composition request returned success=false: {response_data}")
            return None
        
        project_id = response_data.get("project")
        if not project_id:
            logger.error(f"JSON2VIDEO: No project ID in Step 2 response: {response_data}")
            return None
        
        logger.info(f"JSON2VIDEO: Step 2 composition started with project ID: {project_id}")
        
        # Poll for completion
        final_video_url = await check_json2video_status(project_id, max_wait_time=600)  # 10 minutes
        
        if final_video_url:
            logger.info("JSON2VIDEO: Step 2 composition (composed video + music) completed successfully!")
            logger.info(f"JSON2VIDEO: Final video URL with music: {final_video_url}")
            return final_video_url
        else:
            logger.error("JSON2VIDEO: Step 2 composition failed or timed out")
            return None
        
    except Exception as e:
        logger.error(f"JSON2VIDEO: Failed to compose Step 2 (composed video + music): {e}")
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
