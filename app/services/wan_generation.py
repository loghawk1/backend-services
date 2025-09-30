import asyncio
import logging
from typing import List, Dict
import fal_client
from .image_processing import resize_image_with_fal

logger = logging.getLogger(__name__)


async def generate_wan_scene_images_with_fal(nano_banana_prompts: List[str]) -> List[str]:
    """Generate scene images using fal.ai Nano Banana based on nano_banana_prompts"""
    try:
        logger.info(f"WAN: Starting scene image generation for {len(nano_banana_prompts)} scenes...")
        
        # Initialize results list
        scene_image_urls = [""] * len(nano_banana_prompts)
        handlers = []

        # Phase 1: Submit all image requests concurrently
        logger.info("WAN: Phase 1 - Submitting all image generation requests...")
        
        for i, nano_banana_prompt in enumerate(nano_banana_prompts):
            try:
                if not nano_banana_prompt or not nano_banana_prompt.strip():
                    logger.warning(f"WAN: Empty nano_banana_prompt for scene {i+1}")
                    handlers.append(None)
                    continue

                logger.info(f"WAN: Submitting image request for scene {i+1}...")
                logger.info(f"WAN: Nano Banana prompt: {nano_banana_prompt[:100]}...")

                # Submit image generation request using Nano Banana
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/nano-banana",
                    arguments={
                        "prompt": nano_banana_prompt,
                        "num_images": 1,
                        "output_format": "jpeg"
                    }
                )

                handlers.append(handler)
                logger.info(f"WAN: Scene {i+1} image request submitted successfully")

            except Exception as e:
                logger.error(f"WAN: Failed to submit image request for scene {i+1}: {e}")
                handlers.append(None)

        logger.info(f"WAN: Submitted {len([h for h in handlers if h])} out of {len(nano_banana_prompts)} image requests")

        # Phase 2: Wait for all results concurrently
        logger.info("WAN: Phase 2 - Waiting for all image generation results...")

        async def get_image_result(handler, scene_index):
            """Get result from a single image generation handler"""
            if not handler:
                return scene_index, ""

            try:
                logger.info(f"WAN: Waiting for scene {scene_index + 1} image result...")
                result = await asyncio.to_thread(handler.get)

                if result and "images" in result and len(result["images"]) > 0:
                    raw_image_url = result["images"][0]["url"]
                    logger.info(f"WAN: Scene {scene_index + 1} raw image generated: {raw_image_url}")
                    
                    # Resize the Nano Banana output to 9:16 aspect ratio
                    logger.info(f"WAN: Resizing scene {scene_index + 1} image to 9:16...")
                    resized_image_url = await resize_image_with_fal(raw_image_url)
                    
                    if resized_image_url and resized_image_url != raw_image_url:
                        logger.info(f"WAN: Scene {scene_index + 1} image resized successfully: {resized_image_url}")
                    else:
                        logger.warning(f"WAN: Scene {scene_index + 1} image resize failed, using original: {raw_image_url}")
                        resized_image_url = raw_image_url
                    
                    return scene_index, resized_image_url
                else:
                    logger.error(f"WAN: No image generated for scene {scene_index + 1}")
                    logger.debug(f"WAN: Raw result: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"WAN: Failed to get/resize image result for scene {scene_index + 1}: {e}")
                return scene_index, ""

        # Create tasks for all handlers
        tasks = []
        for i, handler in enumerate(handlers):
            task = get_image_result(handler, i)
            tasks.append(task)

        # Wait for all results with timeout
        logger.info(f"WAN: Waiting for {len(tasks)} image generation tasks to complete...")
        try:
            # Add timeout to prevent hanging
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=300  # 5 minutes timeout for image generation
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"WAN: Image generation task failed: {result}")
                    continue

                scene_index, image_url = result
                scene_image_urls[scene_index] = image_url

        except asyncio.TimeoutError:
            logger.error("WAN: Image generation timed out after 5 minutes")
            # Continue with whatever results we have

        successful_images = len([url for url in scene_image_urls if url])
        logger.info(f"WAN: Generated {successful_images} out of {len(nano_banana_prompts)} images successfully")

        # Log final results
        for i, url in enumerate(scene_image_urls):
            if url:
                logger.info(f"WAN: Scene {i+1} final image URL: {url}")
            else:
                logger.warning(f"WAN: Scene {i+1} has no image URL")

        return scene_image_urls

    except Exception as e:
        logger.error(f"WAN: Failed to generate scene images: {e}")
        logger.exception("Full traceback:")
        return []


async def generate_wan_voiceovers_with_fal(elevenlabs_prompts: List[str]) -> List[str]:
    """Generate voiceovers using fal.ai MiniMax Speech 2.5 Turbo based on elevenlabs_prompts"""
    try:
        logger.info(f"WAN: Starting voiceover generation for {len(elevenlabs_prompts)} scenes...")
        
        # Initialize results list
        voiceover_urls = [""] * len(elevenlabs_prompts)
        handlers = []

        # Phase 1: Submit all voiceover requests concurrently
        logger.info("WAN: Phase 1 - Submitting all voiceover generation requests...")
        
        for i, elevenlabs_prompt in enumerate(elevenlabs_prompts):
            try:
                # Extract text from elevenlabs_prompt
                voiceover_text = ""
                if elevenlabs_prompt and "VO (" in elevenlabs_prompt:
                    # Extract text between quotes in the prompt
                    start_quote = elevenlabs_prompt.find('"')
                    if start_quote != -1:
                        end_quote = elevenlabs_prompt.find('"', start_quote + 1)
                        if end_quote != -1:
                            voiceover_text = elevenlabs_prompt[start_quote + 1:end_quote]
                
                if not voiceover_text:
                    logger.warning(f"WAN: No voiceover text found for scene {i+1}")
                    handlers.append(None)
                    continue

                logger.info(f"WAN: Submitting voiceover request for scene {i+1}...")
                logger.info(f"WAN: Text: {voiceover_text[:50]}...")

                # Submit voiceover generation request using MiniMax Speech 2.5 Turbo
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/minimax/preview/speech-2.5-turbo",
                    arguments={
                        "text": voiceover_text,
                        "voice_setting": {
                            "voice_id": "Wise_Woman",
                            "speed": 1.1,  # Slightly faster for UGC feel
                            "vol": 1,
                            "pitch": 0,
                            "english_normalization": False
                        },
                        "output_format": "url"
                    }
                )

                handlers.append(handler)
                logger.info(f"WAN: Scene {i+1} voiceover request submitted successfully")

            except Exception as e:
                logger.error(f"WAN: Failed to submit voiceover request for scene {i+1}: {e}")
                handlers.append(None)

        logger.info(f"WAN: Submitted {len([h for h in handlers if h])} out of {len(elevenlabs_prompts)} voiceover requests")

        # Phase 2: Wait for all results concurrently
        logger.info("WAN: Phase 2 - Waiting for all voiceover generation results...")

        async def get_voiceover_result(handler, scene_index):
            """Get result from a single voiceover generation handler"""
            if not handler:
                return scene_index, ""

            try:
                logger.info(f"WAN: Waiting for scene {scene_index + 1} voiceover result...")
                result = await asyncio.to_thread(handler.get)

                if result and "audio" in result and "url" in result["audio"]:
                    voiceover_url = result["audio"]["url"]
                    logger.info(f"WAN: Scene {scene_index + 1} voiceover generated: {voiceover_url}")
                    return scene_index, voiceover_url
                else:
                    logger.error(f"WAN: No voiceover generated for scene {scene_index + 1}")
                    logger.debug(f"WAN: Raw result: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"WAN: Failed to get voiceover result for scene {scene_index + 1}: {e}")
                return scene_index, ""

        # Create tasks for all handlers
        tasks = []
        for i, handler in enumerate(handlers):
            task = get_voiceover_result(handler, i)
            tasks.append(task)

        # Wait for all results with timeout
        logger.info(f"WAN: Waiting for {len(tasks)} voiceover generation tasks to complete...")
        try:
            # Add timeout to prevent hanging
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=180  # 3 minutes timeout for voiceovers
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"WAN: Voiceover generation task failed: {result}")
                    continue

                scene_index, voiceover_url = result
                voiceover_urls[scene_index] = voiceover_url

        except asyncio.TimeoutError:
            logger.error("WAN: Voiceover generation timed out after 3 minutes")
            # Continue with whatever results we have

        successful_voiceovers = len([url for url in voiceover_urls if url])
        logger.info(f"WAN: Generated {successful_voiceovers} out of {len(elevenlabs_prompts)} voiceovers successfully")

        # Log final results
        for i, url in enumerate(voiceover_urls):
            if url:
                logger.info(f"WAN: Scene {i+1} final voiceover URL: {url}")
            else:
                logger.warning(f"WAN: Scene {i+1} has no voiceover URL")

        return voiceover_urls

    except Exception as e:
        logger.error(f"WAN: Failed to generate voiceovers: {e}")
        logger.exception("Full traceback:")
        return []


async def generate_wan_videos_with_fal(scene_image_urls: List[str], wan2_5_prompts: List[str]) -> List[str]:
    """Generate videos from scene images using fal.ai WAN 2.5 based on wan2_5_prompts"""
    try:
        logger.info(f"WAN: Starting video generation for {len(scene_image_urls)} scene images...")
        
        # Initialize results list
        video_urls = [""] * len(scene_image_urls)
        handlers = []

        # Phase 1: Submit all video requests concurrently
        logger.info("WAN: Phase 1 - Submitting all video generation requests...")
        
        for i, image_url in enumerate(scene_image_urls):
            try:
                if not image_url or i >= len(wan2_5_prompts):
                    logger.warning(f"WAN: Missing image URL or wan2_5_prompt for scene {i+1}")
                    handlers.append(None)
                    continue

                wan2_5_prompt = wan2_5_prompts[i] if wan2_5_prompts[i] else "Animate the static image with subtle movement and UGC-style camera work."

                logger.info(f"WAN: Submitting video request for scene {i+1}...")
                logger.info(f"WAN: Image URL: {image_url}")
                logger.info(f"WAN: WAN 2.5 prompt: {wan2_5_prompt[:100]}...")

                # Submit video generation request using WAN 2.5
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/wan-25-preview/image-to-video",
                    arguments={
                        "prompt": wan2_5_prompt,
                        "image_url": image_url,
                        "resolution": "1080p",
                        "duration": "5",  # 5 seconds per scene
                        "negative_prompt": "professional filming, cinematic production, color grading, high saturation, soft cinematic focus, perfect lighting, 24fps, ultra smooth movement, stabilized shot, studio setup, uncanny valley, stiff movement, fake hands, deformed, aggressive saleswoman, corporate ad, stock footage, watermark, signature, blurry faces.",
                        "enable_prompt_expansion": True
                    }
                )

                handlers.append(handler)
                logger.info(f"WAN: Scene {i+1} video request submitted successfully")

            except Exception as e:
                logger.error(f"WAN: Failed to submit video request for scene {i+1}: {e}")
                handlers.append(None)

        logger.info(f"WAN: Submitted {len([h for h in handlers if h])} out of {len(scene_image_urls)} video requests")

        # Phase 2: Wait for all results concurrently
        logger.info("WAN: Phase 2 - Waiting for all video generation results...")

        async def get_video_result(handler, scene_index):
            """Get result from a single video generation handler"""
            if not handler:
                return scene_index, ""

            try:
                logger.info(f"WAN: Waiting for scene {scene_index + 1} video result...")
                result = await asyncio.to_thread(handler.get)

                if result and "video" in result and "url" in result["video"]:
                    video_url = result["video"]["url"]
                    logger.info(f"WAN: Scene {scene_index + 1} video generated: {video_url}")
                    return scene_index, video_url
                else:
                    logger.error(f"WAN: No video generated for scene {scene_index + 1}")
                    logger.debug(f"WAN: Raw result: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"WAN: Failed to get video result for scene {scene_index + 1}: {e}")
                return scene_index, ""

        # Create tasks for all handlers
        tasks = []
        for i, handler in enumerate(handlers):
            task = get_video_result(handler, i)
            tasks.append(task)

        # Wait for all results with timeout
        logger.info(f"WAN: Waiting for {len(tasks)} video generation tasks to complete...")
        try:
            # Add timeout to prevent hanging (videos take longer)
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=1800  # 30 minutes timeout for video generation
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"WAN: Video generation task failed: {result}")
                    continue

                scene_index, video_url = result
                video_urls[scene_index] = video_url

        except asyncio.TimeoutError:
            logger.error("WAN: Video generation timed out after 30 minutes")
            # Continue with whatever results we have

        successful_videos = len([url for url in video_urls if url])
        logger.info(f"WAN: Generated {successful_videos} out of {len(scene_image_urls)} videos successfully")

        # Log final results
        for i, url in enumerate(video_urls):
            if url:
                logger.info(f"WAN: Scene {i+1} final video URL: {url}")
            else:
                logger.warning(f"WAN: Scene {i+1} has no video URL")

        return video_urls

    except Exception as e:
        logger.error(f"WAN: Failed to generate videos: {e}")
        logger.exception("Full traceback:")
        return []
