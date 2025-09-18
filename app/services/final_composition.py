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
                logger.info(f"COMPOSE: Added voiceover {i + 1} at {timestamp}s")

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