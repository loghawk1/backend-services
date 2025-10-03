import asyncio
import logging
from typing import List, Dict, Optional
import httpx
from ..config import get_settings
from .task_utils import get_resolution_from_aspect_ratio

logger = logging.getLogger(__name__)
settings = get_settings()


async def compose_final_video_with_audio(
    composed_video_url: str,
    voiceover_urls: List[str],
    normalized_music_url: str,
    aspect_ratio: str = "9:16"
) -> str:
    """
    Compose the final video with all audio tracks using JSON2Video:
    - Main video (without audio)
    - 5 voiceovers (6 seconds each at different timestamps)
    - Background music (30 seconds at low volume)
    """
    try:
        logger.info("COMPOSE_JSON2VIDEO: Starting final video composition with all audio tracks...")
        logger.info(f"COMPOSE_JSON2VIDEO: Main video URL: {composed_video_url}")
        logger.info(f"COMPOSE_JSON2VIDEO: Background music URL: {normalized_music_url}")
        logger.info(f"COMPOSE_JSON2VIDEO: Voiceover URLs: {len(voiceover_urls)} voiceovers")

        if not settings.json2video_api_key:
            logger.error("COMPOSE_JSON2VIDEO: JSON2VIDEO_API_KEY not found")
            return composed_video_url

        # Filter out empty voiceover URLs
        valid_voiceover_urls = [url for url in voiceover_urls if url]
        logger.info(f"COMPOSE_JSON2VIDEO: Valid voiceovers: {len(valid_voiceover_urls)} out of {len(voiceover_urls)}")

        # Get dynamic resolution
        width, height = get_resolution_from_aspect_ratio(aspect_ratio)
        logger.info(f"COMPOSE_JSON2VIDEO: Using resolution {width}x{height}")

        # Build scene elements
        scene_elements = []

        # 1. Main video (without audio)
        scene_elements.append({
            "type": "video",
            "src": composed_video_url,
            "start": 0,
            "duration": 30,
            "volume": 0,  # No audio from video
            "resize": "cover"
        })
        logger.info("COMPOSE_JSON2VIDEO: Added main video (30s, no audio)")

        # 2. Voiceovers (6 seconds each at intervals)
        for i, voiceover_url in enumerate(valid_voiceover_urls):
            if i >= 5:  # Only use first 5
                break

            start_time = i * 6  # 0, 6, 12, 18, 24
            scene_elements.append({
                "type": "audio",
                "src": voiceover_url,
                "start": start_time,
                "duration": 6,
                "volume": 2  # High volume for voiceovers
            })
            logger.info(f"COMPOSE_JSON2VIDEO: Added voiceover {i+1} at {start_time}s")

        # 3. Background music
        if normalized_music_url:
            scene_elements.append({
                "type": "audio",
                "src": normalized_music_url,
                "start": 0,
                "duration": 30,
                "volume": 0.2  # Low volume for background
            })
            logger.info("COMPOSE_JSON2VIDEO: Added background music (30s, 20% volume)")

        # Prepare payload
        json_data = {
            "resolution": "custom",
            "width": width,
            "height": height,
            "scenes": [{"elements": scene_elements}]
        }

        logger.info("COMPOSE_JSON2VIDEO: Sending composition request...")

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

        logger.info(f"COMPOSE_JSON2VIDEO: Response status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"COMPOSE_JSON2VIDEO: Request failed: {response.text}")
            return composed_video_url

        response_data = response.json()
        project_id = response_data.get("project")

        if not project_id:
            logger.error(f"COMPOSE_JSON2VIDEO: No project ID: {response_data}")
            return composed_video_url

        logger.info(f"COMPOSE_JSON2VIDEO: Project ID: {project_id}")

        # Poll for completion
        from .json2video_composition import check_json2video_status
        final_video_url = await check_json2video_status(project_id, max_wait_time=300)

        if final_video_url:
            logger.info(f"COMPOSE_JSON2VIDEO: Success! URL: {final_video_url}")
            return final_video_url
        else:
            logger.error("COMPOSE_JSON2VIDEO: Composition failed or timed out")
            return composed_video_url

    except Exception as e:
        logger.error(f"COMPOSE_JSON2VIDEO: Failed: {e}")
        logger.exception("Full traceback:")
        return composed_video_url


async def compose_wan_final_video_with_audio(
    scene_clip_urls: List[str],
    voiceover_urls: List[str],
    aspect_ratio: str = "9:16"
) -> str:
    """
    Compose the final WAN video with all audio tracks using JSON2Video:
    - 6 scene videos (5 seconds each = 30 seconds total)
    - 6 voiceovers (aligned with their respective scenes)
    """
    try:
        logger.info("WAN_COMPOSE_JSON2VIDEO: Starting WAN final video composition...")
        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Scene clips: {len(scene_clip_urls)} videos")
        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Voiceovers: {len(voiceover_urls)} voiceovers")

        # Debug: Log all voiceover URLs
        for i, voiceover_url in enumerate(voiceover_urls):
            if voiceover_url:
                logger.info(f"WAN_COMPOSE_JSON2VIDEO: Voiceover {i+1}: {voiceover_url}")
            else:
                logger.warning(f"WAN_COMPOSE_JSON2VIDEO: Voiceover {i+1} is empty")

        if not settings.json2video_api_key:
            logger.error("WAN_COMPOSE_JSON2VIDEO: JSON2VIDEO_API_KEY not found")
            return ""

        # Filter out empty URLs
        valid_scene_clips = [url for url in scene_clip_urls if url]

        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Valid clips: {len(valid_scene_clips)}/{len(scene_clip_urls)}")
        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Valid voiceovers: {len([v for v in voiceover_urls if v])}/{len(voiceover_urls)}")

        if len([v for v in voiceover_urls if v]) == 0:
            logger.error("WAN_COMPOSE_JSON2VIDEO: No valid voiceovers!")
            logger.error(f"WAN_COMPOSE_JSON2VIDEO: Voiceover URLs: {voiceover_urls}")

        if not valid_scene_clips:
            logger.error("WAN_COMPOSE_JSON2VIDEO: No valid scene clips")
            return ""

        # Get resolution
        width, height = get_resolution_from_aspect_ratio(aspect_ratio)
        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Using resolution {width}x{height}")

        # Build scenes (one scene per video clip)
        scenes = []

        for i in range(min(6, len(valid_scene_clips))):
            scene_elements = []

            # Add video
            if i < len(valid_scene_clips) and valid_scene_clips[i]:
                scene_elements.append({
                    "type": "video",
                    "src": valid_scene_clips[i],
                    "duration": 5,
                    "volume": 0.2,  # Low volume for scene video
                    "resize": "cover"
                })
                logger.info(f"WAN_COMPOSE_JSON2VIDEO: Scene {i+1} video added")

            # Add voiceover
            if i < len(voiceover_urls) and voiceover_urls[i]:
                scene_elements.append({
                    "type": "audio",
                    "src": voiceover_urls[i],
                    "start": 0,
                    "duration": 5,
                    "volume": 2  # High volume for voiceover
                })
                logger.info(f"WAN_COMPOSE_JSON2VIDEO: Scene {i+1} voiceover added")
            else:
                logger.warning(f"WAN_COMPOSE_JSON2VIDEO: Scene {i+1} has no voiceover")

            if scene_elements:
                scenes.append({"elements": scene_elements})

        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Created {len(scenes)} scenes")

        # Prepare payload
        json_data = {
            "resolution": "custom",
            "width": width,
            "height": height,
            "scenes": scenes
        }

        logger.info("WAN_COMPOSE_JSON2VIDEO: Sending composition request...")

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

        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Response status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"WAN_COMPOSE_JSON2VIDEO: Request failed: {response.text}")
            return ""

        response_data = response.json()
        project_id = response_data.get("project")

        if not project_id:
            logger.error(f"WAN_COMPOSE_JSON2VIDEO: No project ID: {response_data}")
            return ""

        logger.info(f"WAN_COMPOSE_JSON2VIDEO: Project ID: {project_id}")

        # Poll for completion
        from .json2video_composition import check_json2video_status
        final_video_url = await check_json2video_status(project_id, max_wait_time=480)

        if final_video_url:
            logger.info(f"WAN_COMPOSE_JSON2VIDEO: Success! URL: {final_video_url}")
            return final_video_url
        else:
            logger.error("WAN_COMPOSE_JSON2VIDEO: Composition failed or timed out")
            return ""

    except Exception as e:
        logger.error(f"WAN_COMPOSE_JSON2VIDEO: Failed: {e}")
        logger.exception("Full traceback:")
        return ""
