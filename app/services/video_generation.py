import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def generate_videos_with_fal(scene_image_urls: List[str], video_prompts: List[str]) -> List[str]:
    """Generate videos from scene images using fal.ai MiniMax Hailuo-02 with combined video prompts"""
    try:
        logger.info(f"FAL: Starting video generation for {len(scene_image_urls)} scene images...")
        
        # Initialize results list
        video_urls = [""] * len(scene_image_urls)
        handlers = []

        # Phase 1: Submit all video requests concurrently
        logger.info("FAL: Phase 1 - Submitting all video generation requests...")
        
        for i, image_url in enumerate(scene_image_urls):
            try:
                if i >= len(video_prompts):
                    logger.warning(f"FAL: No video prompt available for scene {i+1}")
                    handlers.append(None)
                    continue

                # Use the combined video prompt string directly
                prompt = video_prompts[i] if video_prompts[i] else "Create a dynamic product showcase video from this image. Add smooth camera movements and professional lighting effects."

                logger.info(f"FAL: Submitting video request for scene {i+1}...")
                logger.info(f"FAL: Image URL: {image_url}")
                logger.info(f"FAL: Visual description: {prompt[:100]}...")

                # Submit video generation request using MiniMax Hailuo-02
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/minimax/hailuo-02/standard/image-to-video",
                    arguments={
                        "prompt": prompt,
                        "image_url": image_url,
                        "duration": "6",            # 6 seconds
                        "prompt_optimizer": True,   # keep true for better results
                        "resolution": "512P"        # default high resolution
                    }
                )

                handlers.append(handler)
                logger.info(f"FAL: Scene {i+1} video request submitted successfully")

            except Exception as e:
                logger.error(f"FAL: Failed to submit video request for scene {i+1}: {e}")
                handlers.append(None)

        logger.info(f"FAL: Submitted {len([h for h in handlers if h])} out of {len(scene_image_urls)} video requests")

        # Phase 2: Wait for all results concurrently
        logger.info("FAL: Phase 2 - Waiting for all video generation results...")

        async def get_video_result(handler, scene_index):
            """Get result from a single video generation handler"""
            if not handler:
                return scene_index, ""

            try:
                logger.info(f"FAL: Waiting for scene {scene_index + 1} video result...")
                result = await asyncio.to_thread(handler.get)

                if result and "video" in result and "url" in result["video"]:
                    video_url = result["video"]["url"]
                    logger.info(f"FAL: Scene {scene_index + 1} video generated: {video_url}")
                    return scene_index, video_url
                else:
                    logger.error(f"FAL: No video generated for scene {scene_index + 1}")
                    logger.debug(f"FAL: Raw result: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"FAL: Failed to get video result for scene {scene_index + 1}: {e}")
                return scene_index, ""

        # Create tasks for all handlers
        tasks = []
        for i, handler in enumerate(handlers):
            task = get_video_result(handler, i)
            tasks.append(task)

        # Wait for all results with timeout
        logger.info(f"FAL: Waiting for {len(tasks)} video generation tasks to complete...")
        try:
            # Add timeout to prevent hanging (videos take longer than images)
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=1800  # 30 minutes timeout for video generation
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"FAL: Video generation task failed: {result}")
                    continue

                scene_index, video_url = result
                video_urls[scene_index] = video_url

        except asyncio.TimeoutError:
            logger.error("FAL: Video generation timed out after 30 minutes")
            # Continue with whatever results we have

        successful_videos = len([url for url in video_urls if url])
        logger.info(f"FAL: Generated {successful_videos} out of {len(scene_image_urls)} videos successfully")

        # Log final results
        for i, url in enumerate(video_urls):
            if url:
                logger.info(f"FAL: Scene {i+1} final video URL: {url}")
            else:
                logger.warning(f"FAL: Scene {i+1} has no video URL")

        return video_urls

    except Exception as e:
        logger.error(f"FAL: Failed to generate videos: {e}")
        logger.exception("Full traceback:")
        return []


async def compose_final_video(video_urls: List[str]) -> str:
    """Compose final video from 5 scene videos using fal.ai ffmpeg compose"""
    try:
        logger.info(f"FAL: Starting final video composition from {len(video_urls)} scene videos...")
        
        # Filter out empty URLs
        valid_video_urls = [url for url in video_urls if url]
        logger.info(f"FAL: Using {len(valid_video_urls)} valid video URLs for composition")
        
        if not valid_video_urls:
            logger.error("FAL: No valid video URLs for composition")
            return ""
        
        # Create tracks for composition using the official API format
        # Single video track with keyframes for each scene
        keyframes = []
        
        for i, video_url in enumerate(valid_video_urls):
            if i >= 5:  # Only use first 5 videos
                break
                
            timestamp = i * 6000  # Convert to milliseconds (6 seconds each)
            keyframe = {
                "url": video_url,
                "timestamp": timestamp,
                "duration": 6000  # 6 seconds in milliseconds
            }
            keyframes.append(keyframe)
            logger.info(f"FAL: Added scene {i+1} at timestamp {timestamp/1000}s")
        
        # Create the track structure according to official docs
        tracks = [
            {
                "id": "main_video_track",
                "type": "video",
                "keyframes": keyframes
            }
        ]
        
        logger.info(f"FAL: Total composition duration: {len(keyframes) * 6} seconds")
        logger.info("FAL: Submitting composition request...")
        
        # Submit the composition request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/ffmpeg-api/compose",
            arguments={
                "tracks": tracks
            }
        )
        
        logger.info("FAL: Waiting for composition result...")
        result = await asyncio.to_thread(handler.get)
        
        # Extract the composed video URL
        if result and "video_url" in result:
            composed_video_url = result["video_url"]
            logger.info(f"FAL: Final video composition successful!")
            logger.info(f"FAL: Composed video URL: {composed_video_url}")
            
            # Log thumbnail if available
            if "thumbnail_url" in result:
                logger.info(f"FAL: Thumbnail URL: {result['thumbnail_url']}")
            
            return composed_video_url
        else:
            logger.error("FAL: Composition failed - no video_url in result")
            logger.debug(f"FAL: Raw result: {result}")
            return ""
    
    except Exception as e:
        logger.error(f"FAL: Failed to compose final video: {e}")
        logger.exception("Full traceback:")
        return ""
