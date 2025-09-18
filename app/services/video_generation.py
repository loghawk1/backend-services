import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def generate_videos_with_fal(scene_image_urls: List[str], scenes: List[Dict]) -> List[str]:
    """Generate videos from scene images using fal.ai MiniMax Hailuo-02 (standard, 768p)"""
    try:
        logger.info(f"FAL: Starting video generation for {len(scene_image_urls)} scene images...")

        # Initialize results list
        video_urls = [""] * len(scene_image_urls)
        handlers = []

        # Phase 1: Submit all video generation requests concurrently
        logger.info("FAL: Phase 1 - Submitting all video generation requests...")

        for i, image_url in enumerate(scene_image_urls):
            if not image_url:
                logger.warning(f"FAL: No image URL for scene {i + 1}, skipping video generation")
                handlers.append(None)
                continue

            try:
                # Get the visual description for this scene
                visual_description = ""
                if i < len(scenes):
                    visual_description = scenes[i].get("visual_description", "")

                # Use visual description as prompt, fallback to generic prompt
                prompt = visual_description if visual_description else "Create a dynamic product showcase video from this image. Add smooth camera movements and professional lighting effects."

                logger.info(f"FAL: Submitting video request for scene {i + 1}...")
                logger.info(f"FAL: Using image: {image_url}")
                logger.info(f"FAL: Using prompt: {prompt[:100]}...")

                # Submit video generation request (non-blocking)
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/minimax/hailuo-02/standard/image-to-video",
                    arguments={
                        "prompt": prompt,
                        "image_url": image_url,
                        "duration": "6",  # allowed values: "6" or "10"
                        "prompt_optimizer": True,  # keep true for better results
                        "resolution": "768P"  # default high resolution
                    }
                )

                handlers.append(handler)
                logger.info(f"FAL: Scene {i + 1} video request submitted successfully")

            except Exception as e:
                logger.error(f"FAL: Failed to submit video request for scene {i + 1}: {e}")
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
            # Add timeout to prevent hanging
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=600  # 10 minutes timeout
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"FAL: Video generation task failed: {result}")
                    continue

                scene_index, video_url = result
                video_urls[scene_index] = video_url

        except asyncio.TimeoutError:
            logger.error("FAL: Video generation timed out after 10 minutes")
            # Continue with whatever results we have

        successful_videos = len([url for url in video_urls if url])
        logger.info(f"FAL: Generated {successful_videos} out of {len(scene_image_urls)} videos successfully")

        # Log final results
        for i, url in enumerate(video_urls):
            if url:
                logger.info(f"FAL: Scene {i + 1} final video URL: {url}")
            else:
                logger.warning(f"FAL: Scene {i + 1} has no video URL")

        return video_urls

    except Exception as e:
        logger.error(f"FAL: Failed to generate videos: {e}")
        logger.exception("Full traceback:")
        return []


async def compose_final_video(video_urls: List[str]) -> str:
    """Compose/merge the 5 scene videos into one final video using fal.ai ffmpeg-api/compose"""
    try:
        logger.info(f"FAL: Starting video composition for {len(video_urls)} videos...")

        # Filter out empty URLs
        valid_video_urls = [url for url in video_urls if url]

        if not valid_video_urls:
            logger.error("FAL: No valid video URLs to compose")
            return ""

        if len(valid_video_urls) < 5:
            logger.warning(f"FAL: Only {len(valid_video_urls)} out of 5 videos available for composition")

        logger.info(f"FAL: Composing {len(valid_video_urls)} videos...")

        # Create keyframes for video concatenation
        # Each video is 6 seconds, so timestamps are: 0, 6, 12, 18, 24
        keyframes = []
        for i, video_url in enumerate(valid_video_urls):
            timestamp = i * 6  # Each video is 6 seconds
            keyframes.append({
                "url": video_url,
                "timestamp": timestamp,
                "duration": 6
            })
            logger.info(f"FAL: Video {i + 1} at timestamp {timestamp}s: {video_url}")

        # Submit video concatenation request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/ffmpeg-api/compose",
            arguments={
                "tracks": [
                    {
                        "id": "main",
                        "type": "video",
                        "keyframes": keyframes
                    }
                ]
            }
        )

        logger.info("FAL: Waiting for video concatenation result...")
        result = await asyncio.to_thread(handler.get)

        # Extract concatenated video URL
        if result and "video_url" in result:
            concatenated_video_url = result["video_url"]
            logger.info(f"FAL: Video concatenation successful: {concatenated_video_url}")
            return concatenated_video_url
        else:
            logger.error("FAL: Video concatenation failed, using first video as fallback")
            return valid_video_urls[0] if valid_video_urls else ""

    except Exception as e:
        logger.error(f"FAL: Failed to concatenate videos: {e}")
        logger.exception("Full traceback:")
        # Return first video as fallback
        valid_urls = [url for url in video_urls if url]
        return valid_urls[0] if valid_urls else ""


async def generate_videos_with_fal(scene_image_urls: List[str], scenes: List[Dict]) -> List[str]:
    """Generate videos from scene images using fal.ai MiniMax Hailuo-02 (standard, 768p)"""
    try:
        logger.info(f"FAL: Starting video generation for {len(scene_image_urls)} scene images...")

        # Initialize results list
        video_urls = [""] * len(scene_image_urls)
        handlers = []

        # Phase 1: Submit all video generation requests concurrently
        logger.info("FAL: Phase 1 - Submitting all video generation requests...")

        for i, image_url in enumerate(scene_image_urls):
            if not image_url:
                logger.warning(f"FAL: No image URL for scene {i + 1}, skipping video generation")
                handlers.append(None)
                continue

            try:
                # Get the visual description for this scene
                visual_description = ""
                if i < len(scenes):
                    visual_description = scenes[i].get("visual_description", "")

                # Use visual description as prompt, fallback to generic prompt
                prompt = visual_description if visual_description else "Create a dynamic product showcase video from this image. Add smooth camera movements and professional lighting effects."

                logger.info(f"FAL: Submitting video request for scene {i + 1}...")
                logger.info(f"FAL: Using image: {image_url}")
                logger.info(f"FAL: Using prompt: {prompt[:100]}...")

                # Submit video generation request (non-blocking)
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/minimax/hailuo-02/standard/image-to-video",
                    arguments={
                        "prompt": prompt,
                        "image_url": image_url,
                        "duration": "6",  # allowed values: "6" or "10"
                        "prompt_optimizer": True,  # keep true for better results
                        "resolution": "512P"  # default high resolution
                    }
                )

                handlers.append(handler)
                logger.info(f"FAL: Scene {i + 1} video request submitted successfully")

            except Exception as e:
                logger.error(f"FAL: Failed to submit video request for scene {i + 1}: {e}")
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
            # Add timeout to prevent hanging
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=600  # 10 minutes timeout
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"FAL: Video generation task failed: {result}")
                    continue

                scene_index, video_url = result
                video_urls[scene_index] = video_url

        except asyncio.TimeoutError:
            logger.error("FAL: Video generation timed out after 10 minutes")
            # Continue with whatever results we have

        successful_videos = len([url for url in video_urls if url])
        logger.info(f"FAL: Generated {successful_videos} out of {len(scene_image_urls)} videos successfully")

        # Log final results
        for i, url in enumerate(video_urls):
            if url:
                logger.info(f"FAL: Scene {i + 1} final video URL: {url}")
            else:
                logger.warning(f"FAL: Scene {i + 1} has no video URL")

        return video_urls

    except Exception as e:
        logger.error(f"FAL: Failed to generate videos: {e}")
        logger.exception("Full traceback:")
        return []


async def compose_final_video(video_urls: List[str]) -> str:
    """Compose/merge the 5 scene videos into one final video using fal.ai ffmpeg-api/compose"""
    try:
        logger.info(f"FAL: Starting video composition for {len(video_urls)} videos...")

        # Filter out empty URLs
        valid_video_urls = [url for url in video_urls if url]

        if not valid_video_urls:
            logger.error("FAL: No valid video URLs to compose")
            return ""

        if len(valid_video_urls) < 5:
            logger.warning(f"FAL: Only {len(valid_video_urls)} out of 5 videos available for composition")

        logger.info(f"FAL: Composing {len(valid_video_urls)} videos...")

        # Create keyframes for video concatenation
        # Each video is 6 seconds, so timestamps are: 0, 6, 12, 18, 24
        keyframes = []
        for i, video_url in enumerate(valid_video_urls):
            timestamp = i * 6  # Each video is 6 seconds
            keyframes.append({
                "url": video_url,
                "timestamp": timestamp,
                "duration": 6
            })
            logger.info(f"FAL: Video {i + 1} at timestamp {timestamp}s: {video_url}")

        # Submit video concatenation request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/ffmpeg-api/compose",
            arguments={
                "tracks": [
                    {
                        "id": "main",
                        "type": "video",
                        "keyframes": keyframes
                    }
                ]
            }
        )

        logger.info("FAL: Waiting for video concatenation result...")
        result = await asyncio.to_thread(handler.get)

        # Extract concatenated video URL
        if result and "video_url" in result:
            concatenated_video_url = result["video_url"]
            logger.info(f"FAL: Video concatenation successful: {concatenated_video_url}")
            return concatenated_video_url
        else:
            logger.error("FAL: Video concatenation failed, using first video as fallback")
            return valid_video_urls[0] if valid_video_urls else ""

    except Exception as e:
        logger.error(f"FAL: Failed to concatenate videos: {e}")
        logger.exception("Full traceback:")
        # Return first video as fallback
        valid_urls = [url for url in video_urls if url]
        return valid_urls[0] if valid_urls else ""