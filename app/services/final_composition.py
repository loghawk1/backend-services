import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def compose_final_video_with_audio(
    composed_video_url: str, 
    voiceover_urls: List[str], 
    normalized_music_url: str
) -> str:
    """
    Compose the final video with all audio tracks:
    - Main video (without audio)
    - 5 voiceovers (6 seconds each at different timestamps)
    - Background music (30 seconds at low volume)
    """
    try:
        logger.info("COMPOSE: Starting final video composition with all audio tracks...")
        logger.info(f"COMPOSE: Main video URL: {composed_video_url}")
        logger.info(f"COMPOSE: Background music URL: {normalized_music_url}")
        logger.info(f"COMPOSE: Voiceover URLs: {len(voiceover_urls)} voiceovers")

        # Filter out empty voiceover URLs
        valid_voiceover_urls = [url for url in voiceover_urls if url]
        logger.info(f"COMPOSE: Valid voiceovers: {len(valid_voiceover_urls)} out of {len(voiceover_urls)}")

        # Build the tracks for composition
        tracks = []

        # 1. Main video track (without audio)
        video_track = {
            "id": "video_main",
            "type": "video",
            "keyframes": [
                {
                    "url": composed_video_url,
                    "timestamp": 0,
                    "duration": 30,
                    "include_audio": False  # Exclude original audio
                }
            ]
        }
        tracks.append(video_track)
        logger.info("COMPOSE: Added main video track (30s, no audio)")

        # 2. Voiceover track (5 voiceovers at 6-second intervals)
        if valid_voiceover_urls:
            voiceover_keyframes = []
            
            for i, voiceover_url in enumerate(valid_voiceover_urls):
                if i >= 5:  # Only use first 5 voiceovers
                    break
                    
                timestamp = i * 6  # 0, 6, 12, 18, 24 seconds
                keyframe = {
                    "url": voiceover_url,
                    "timestamp": timestamp,
                    "duration": 6,
                    "volume": 1.0  # Full volume for voiceovers
                }
                voiceover_keyframes.append(keyframe)
                logger.info(f"COMPOSE: Added voiceover {i+1} at {timestamp}s")

            voiceover_track = {
                "id": "voiceover",
                "type": "audio",
                "keyframes": voiceover_keyframes
            }
            tracks.append(voiceover_track)
            logger.info(f"COMPOSE: Added voiceover track with {len(voiceover_keyframes)} segments")

        # 3. Background music track (full 30 seconds at low volume)
        if normalized_music_url:
            background_music_track = {
                "id": "background_music",
                "type": "audio",
                "keyframes": [
                    {
                        "url": normalized_music_url,
                        "timestamp": 0,
                        "duration": 30,
                        "volume": 0.1  # Low volume (10%) for background music
                    }
                ]
            }
            tracks.append(background_music_track)
            logger.info("COMPOSE: Added background music track (30s, 10% volume)")

        logger.info(f"COMPOSE: Total tracks to compose: {len(tracks)}")

        # Submit the composition request
        logger.info("COMPOSE: Submitting final composition request...")
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/ffmpeg-api/compose",
            arguments={
                "compose_mode": "timeline",
                "tracks": tracks
            }
        )

        logger.info("COMPOSE: Waiting for final composition result...")
        result = await asyncio.to_thread(handler.get)

        # Extract the final video URL
        if result and "video_url" in result:
            final_video_url = result["video_url"]
            logger.info(f"COMPOSE: Final video composition successful!")
            logger.info(f"COMPOSE: Final video URL: {final_video_url}")
            
            # Log thumbnail if available
            if "thumbnail_url" in result:
                logger.info(f"COMPOSE: Thumbnail URL: {result['thumbnail_url']}")
            
            return final_video_url
        else:
            logger.error("COMPOSE: Final composition failed - no video_url in result")
            logger.debug(f"COMPOSE: Raw result: {result}")
            return composed_video_url  # Return original composed video as fallback

    except Exception as e:
        logger.error(f"COMPOSE: Failed to compose final video with audio: {e}")
        logger.exception("Full traceback:")
        return composed_video_url  # Return original composed video as fallback


async def compose_wan_final_video_with_audio(
    scene_clip_urls: List[str], 
    voiceover_urls: List[str]
) -> str:
    """
    Compose the final WAN video with all audio tracks:
    - 6 scene videos (5 seconds each = 30 seconds total)
    - 6 voiceovers (aligned with their respective scenes)
    """
    try:
        logger.info("WAN_COMPOSE: Starting WAN final video composition with all audio tracks...")
        logger.info(f"WAN_COMPOSE: Scene clip URLs: {len(scene_clip_urls)} videos")
        logger.info(f"WAN_COMPOSE: Voiceover URLs: {len(voiceover_urls)} voiceovers")

        # Filter out empty scene clip URLs
        valid_scene_clips = [url for url in scene_clip_urls if url]
        valid_voiceovers = [url for url in voiceover_urls if url]
        
        logger.info(f"WAN_COMPOSE: Valid scene clips: {len(valid_scene_clips)} out of {len(scene_clip_urls)}")
        logger.info(f"WAN_COMPOSE: Valid voiceovers: {len(valid_voiceovers)} out of {len(voiceover_urls)}")

        if not valid_scene_clips:
            logger.error("WAN_COMPOSE: No valid scene clips for composition")
            return ""

        # Build the tracks for composition
        tracks = []

        # 1. Video track with all 6 scenes (5 seconds each)
        video_keyframes = []
        for i, scene_clip_url in enumerate(valid_scene_clips):
            if i >= 6:  # Only use first 6 videos
                break
                
            timestamp = i * 5  # 0, 5, 10, 15, 20, 25 seconds
            keyframe = {
                "url": scene_clip_url,
                "timestamp": timestamp,
                "duration": 5,
                "include_audio": False  # Exclude original audio from scene clips
            }
            video_keyframes.append(keyframe)
            logger.info(f"WAN_COMPOSE: Added scene {i+1} at timestamp {timestamp}s")

        video_track = {
            "id": "wan_video_main",
            "type": "video",
            "keyframes": video_keyframes
        }
        tracks.append(video_track)
        logger.info(f"WAN_COMPOSE: Added main video track with {len(video_keyframes)} scenes (30s total)")

        # 2. Voiceover track (6 voiceovers at 5-second intervals)
        if valid_voiceovers:
            voiceover_keyframes = []
            
            for i, voiceover_url in enumerate(valid_voiceovers):
                if i >= 6:  # Only use first 6 voiceovers
                    break
                    
                timestamp = i * 5  # 0, 5, 10, 15, 20, 25 seconds
                keyframe = {
                    "url": voiceover_url,
                    "timestamp": timestamp,
                    "duration": 5,  # Allow up to 5 seconds per voiceover
                    "volume": 1.0  # Full volume for voiceovers
                }
                voiceover_keyframes.append(keyframe)
                logger.info(f"WAN_COMPOSE: Added voiceover {i+1} at {timestamp}s")

            voiceover_track = {
                "id": "wan_voiceover",
                "type": "audio",
                "keyframes": voiceover_keyframes
            }
            tracks.append(voiceover_track)
            logger.info(f"WAN_COMPOSE: Added voiceover track with {len(voiceover_keyframes)} segments")

        logger.info(f"WAN_COMPOSE: Total tracks to compose: {len(tracks)}")

        # Submit the composition request
        logger.info("WAN_COMPOSE: Submitting WAN final composition request...")
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/ffmpeg-api/compose",
            arguments={
                "compose_mode": "timeline",
                "tracks": tracks
            }
        )

        logger.info("WAN_COMPOSE: Waiting for WAN final composition result...")
        result = await asyncio.to_thread(handler.get)

        # Extract the final video URL
        if result and "video_url" in result:
            final_video_url = result["video_url"]
            logger.info(f"WAN_COMPOSE: WAN final video composition successful!")
            logger.info(f"WAN_COMPOSE: Final video URL: {final_video_url}")
            
            # Log thumbnail if available
            if "thumbnail_url" in result:
                logger.info(f"WAN_COMPOSE: Thumbnail URL: {result['thumbnail_url']}")
            
            return final_video_url
        else:
            logger.error("WAN_COMPOSE: WAN final composition failed - no video_url in result")
            logger.debug(f"WAN_COMPOSE: Raw result: {result}")
            return ""

    except Exception as e:
        logger.error(f"WAN_COMPOSE: Failed to compose WAN final video with audio: {e}")
        logger.exception("Full traceback:")
        return ""
