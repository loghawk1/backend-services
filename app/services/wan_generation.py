import asyncio
import logging
from typing import List, Dict
import fal_client
from http import HTTPStatus
from dashscope import VideoSynthesis
import dashscope
from app.config import get_settings

logger = logging.getLogger(__name__)


async def generate_wan_scene_images_with_fal(nano_banana_prompts: List[str], base_image_url: str, aspect_ratio: str = "9:16") -> List[str]:
    """Generate scene images using fal.ai Gemini edit model based on nano_banana_prompts and resized base image from frontend"""
    try:
        logger.info(f"WAN_IMAGE: Starting scene image generation for {len(nano_banana_prompts)} scenes using Gemini edit with aspect ratio {aspect_ratio}...")
        logger.info(f"WAN_IMAGE: Base image URL: {base_image_url}")
        
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
                logger.info(f"WAN: Gemini edit prompt: {nano_banana_prompt[:100]}...")
                logger.info(f"WAN: Using aspect ratio: {aspect_ratio}")

                # Submit image generation request using Gemini edit model
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/gemini-25-flash-image/edit",
                    arguments={
                        "prompt": f"{nano_banana_prompt},Authentic UGC style video, shot on smartphone, natural lighting, a bit shaky, no professional camera look. Please generate a still image with a fixed, locked composition (Static Shot), keeping the main subject perfectly centered. The camera must not move. The image must use a full Vertical 9:16 aspect ratio. The technical quality should be ultra-high fidelity, sharp, and hyper-realistic (8K level). Use soft, consistent natural lighting throughout. Crucially, this image must be completely clean—explicitly exclude all digital noise, grain, blurriness, or visual artifacts. Finally, ensure all anatomy is correct (e.g., no distorted hands or faces).",
                        "image_urls": [base_image_url],
                        "num_images": 1,
                        "output_format": "jpeg",
                        "aspect_ratio": aspect_ratio
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
                    image_url = result["images"][0]["url"]
                    logger.info(f"WAN: Scene {scene_index + 1} image generated using Gemini edit: {image_url}")
                    return scene_index, image_url
                else:
                    logger.error(f"WAN: No image generated for scene {scene_index + 1}")
                    logger.debug(f"WAN: Raw result: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"WAN: Failed to get image result for scene {scene_index + 1}: {e}")
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
        logger.info(f"WAN: Generated {successful_images} out of {len(nano_banana_prompts)} images successfully using Gemini edit")

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


async def generate_wan_voiceovers_with_fal(wan_scenes: List[Dict]) -> List[str]:
    """Generate voiceovers using fal.ai MiniMax Speech 2.5 Turbo based on WAN scenes with emotion and voice_id support"""
    try:
        logger.info(f"WAN_VOICEOVER: Starting voiceover generation for {len(wan_scenes)} scenes...")

        # Debug: Log all input scenes to see what GPT-4 generated
        logger.info("WAN_VOICEOVER: === Input Scenes Debug ===")
        for i, scene in enumerate(wan_scenes):
            elevenlabs_prompt = scene.get("elevenlabs_prompt", "")
            emotion = scene.get("eleven_labs_emotion", "")
            voice_id = scene.get("eleven_labs_voice_id", "")
            logger.info(f"WAN_VOICEOVER: Scene {i+1} elevenlabs_prompt: '{elevenlabs_prompt}'")
            logger.info(f"WAN_VOICEOVER: Scene {i+1} emotion: '{emotion}'")
            logger.info(f"WAN_VOICEOVER: Scene {i+1} voice_id: '{voice_id}'")
        logger.info("WAN_VOICEOVER: === End Input Scenes Debug ===")
        
        # Initialize results list
        voiceover_urls = [""] * len(wan_scenes)
        handlers = []

        # Phase 1: Submit all voiceover requests concurrently
        logger.info("WAN: Phase 1 - Submitting all voiceover generation requests...")
        
        for i, scene in enumerate(wan_scenes):
            try:
                # Extract voiceover data from scene
                logger.info(f"WAN: === Processing Scene {i+1} ===")
                logger.info(f"WAN: Full scene data: {scene}")
                
                elevenlabs_prompt = scene.get("elevenlabs_prompt", "")
                eleven_labs_emotion = scene.get("eleven_labs_emotion", "neutral")
                eleven_labs_voice_id = scene.get("eleven_labs_voice_id", "Wise_Woman")

                logger.info(f"WAN_VOICEOVER: Scene {i+1} extracted elevenlabs_prompt: '{elevenlabs_prompt}'")
                logger.info(f"WAN_VOICEOVER: Scene {i+1} extracted eleven_labs_emotion: '{eleven_labs_emotion}'")
                logger.info(f"WAN_VOICEOVER: Scene {i+1} extracted eleven_labs_voice_id: '{eleven_labs_voice_id}'")

                # Add fallback if prompt is empty
                if not elevenlabs_prompt or not elevenlabs_prompt.strip():
                    elevenlabs_prompt = f"This is scene {i+1} of the video."
                    logger.warning(f"WAN_VOICEOVER: Empty elevenlabs_prompt for scene {i+1}, using fallback: '{elevenlabs_prompt}'")

                # Use the elevenlabs_prompt as speech text directly
                voiceover_text = elevenlabs_prompt.strip()

                logger.info(f"WAN_VOICEOVER: Final speech text for scene {i+1}: '{voiceover_text}'")

                # At this point voiceover_text should never be empty due to fallback above
                if not voiceover_text:
                    logger.error(f"WAN_VOICEOVER: CRITICAL - No speech text after fallback for scene {i+1}!")
                    handlers.append(None)
                    continue
                
                # Truncate if too long (max 5000 characters according to API docs)
                if len(voiceover_text) > 5000:
                    voiceover_text = voiceover_text[:5000]
                    logger.warning(f"WAN: Truncated elevenlabs_prompt for scene {i+1} to 5000 characters")

                logger.info(f"WAN_VOICEOVER: Submitting voiceover request for scene {i+1}...")
                logger.info(f"WAN_VOICEOVER: Speech text length: {len(voiceover_text)} characters")
                logger.info(f"WAN_VOICEOVER: Speech text preview: {voiceover_text[:100]}...")

                # Map voice_id to MiniMax compatible voice names
                voice_mapping = {
                    "Wise_Woman": "Wise_Woman",
                    "Deep_Voice_Man": "Deep_Voice_Man", 
                }
                
                # Get MiniMax voice name
                minimax_voice = voice_mapping.get(eleven_labs_voice_id, "Wise_Woman")
                logger.info(f"WAN_VOICEOVER: Scene {i+1} mapped voice {eleven_labs_voice_id} -> {minimax_voice}")

                # Map emotion to MiniMax compatible emotions
                emotion_mapping = {
                    "happy": "happy",
                    "sad": "sad",
                    "angry": "angry",
                    "fearful": "fearful",
                    "disgusted": "disgusted",
                    "surprised": "surprised",
                    "neutral": "neutral"
                }

                minimax_emotion = emotion_mapping.get(eleven_labs_emotion, "neutral")
                logger.info(f"WAN_VOICEOVER: Scene {i+1} mapped emotion {eleven_labs_emotion} -> {minimax_emotion}")

                # Submit voiceover generation request using MiniMax Speech 2.5 Turbo with proper voice mapping
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/minimax/preview/speech-2.5-turbo",
                    arguments={
                        "text": voiceover_text,  # Use extracted speech text only
                        "voice_setting": {
                            "voice_id": minimax_voice,
                            "speed": 1.2,
                            "vol": 1.0,
                            "pitch": 0,
                            "emotion": minimax_emotion
                        },
                        "output_format": "url"  # Get URL response instead of hex
                    }
                )

                handlers.append(handler)
                logger.info(f"WAN_VOICEOVER: Scene {i+1} voiceover request submitted successfully using MiniMax Speech 2.5 Turbo")

            except Exception as e:
                logger.error(f"WAN_VOICEOVER: Failed to submit voiceover request for scene {i+1}: {e}")
                logger.exception(f"WAN_VOICEOVER: Full traceback for scene {i+1}:")
                handlers.append(None)

        successful_submissions = len([h for h in handlers if h])
        logger.info(f"WAN_VOICEOVER: Submitted {successful_submissions} out of {len(wan_scenes)} voiceover requests")

        if successful_submissions == 0:
            logger.error("WAN_VOICEOVER: CRITICAL - No voiceover requests were submitted successfully!")
            return ["" for _ in wan_scenes]

        # Phase 2: Wait for all results concurrently
        logger.info("WAN_VOICEOVER: Phase 2 - Waiting for all voiceover generation results...")

        async def get_voiceover_result(handler, scene_index):
            """Get result from a single voiceover generation handler"""
            if not handler:
                return scene_index, ""

            try:
                logger.info(f"WAN_VOICEOVER: Waiting for scene {scene_index + 1} voiceover result...")
                result = await asyncio.to_thread(handler.get)

                # Log the full result to debug the response format
                logger.info(f"WAN_VOICEOVER: Scene {scene_index + 1} raw API result: {result}")

                if result and "audio" in result and "url" in result["audio"]:
                    voiceover_url = result["audio"]["url"]
                    logger.info(f"WAN_VOICEOVER: Scene {scene_index + 1} voiceover generated successfully: {voiceover_url}")
                    return scene_index, voiceover_url
                else:
                    logger.error(f"WAN_VOICEOVER: No voiceover generated for scene {scene_index + 1}")
                    logger.error(f"WAN_VOICEOVER: Unexpected result format. Expected {{'audio': {{'url': '...'}}}}, got: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"WAN_VOICEOVER: Failed to get voiceover result for scene {scene_index + 1}: {e}")
                logger.exception(f"WAN_VOICEOVER: Full traceback for scene {scene_index + 1}:")
                return scene_index, ""

        # Create tasks for all handlers
        tasks = []
        for i, handler in enumerate(handlers):
            task = get_voiceover_result(handler, i)
            tasks.append(task)

        # Wait for all results with timeout
        logger.info(f"WAN_VOICEOVER: Waiting for {len(tasks)} voiceover generation tasks to complete...")
        try:
            # Add timeout to prevent hanging
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=300  # 5 minutes timeout for voiceovers (increased buffer)
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"WAN_VOICEOVER: Voiceover generation task failed with exception: {result}")
                    logger.exception(f"WAN_VOICEOVER: Exception details:")
                    continue

                scene_index, voiceover_url = result
                voiceover_urls[scene_index] = voiceover_url
                if voiceover_url:
                    logger.info(f"WAN_VOICEOVER: Successfully stored voiceover URL for scene {scene_index + 1}")
                else:
                    logger.warning(f"WAN_VOICEOVER: Empty voiceover URL for scene {scene_index + 1}")

        except asyncio.TimeoutError:
            logger.error("WAN_VOICEOVER: Voiceover generation timed out after 5 minutes")
            # Continue with whatever results we have

        successful_voiceovers = len([url for url in voiceover_urls if url])
        logger.info(f"WAN_VOICEOVER: === Final Voiceover Results ===")
        logger.info(f"WAN_VOICEOVER: Generated {successful_voiceovers} out of {len(wan_scenes)} voiceovers successfully")

        # Log final results
        for i, url in enumerate(voiceover_urls):
            if url:
                logger.info(f"WAN_VOICEOVER: Scene {i+1} final voiceover URL: {url}")
            else:
                logger.error(f"WAN_VOICEOVER: Scene {i+1} has NO voiceover URL - THIS IS A PROBLEM!")
        logger.info(f"WAN_VOICEOVER: === End Final Voiceover Results ===")

        if successful_voiceovers == 0:
            logger.error("WAN_VOICEOVER: CRITICAL - No voiceovers were generated! Returning empty list.")

        return voiceover_urls

    except Exception as e:
        logger.error(f"WAN_VOICEOVER: Failed to generate voiceovers: {e}")
        logger.exception("WAN_VOICEOVER: Full traceback:")
        return []


async def generate_wan_videos_with_fal(scene_image_urls: List[str], wan2_5_prompts: List[str]) -> List[str]:
    """Generate videos from scene images using Alibaba DashScope WAN 2.2 i2v-plus based on wan2_5_prompts"""
    try:
        settings = get_settings()
        dashscope.base_http_api_url = 'https://dashscope-intl.aliyuncs.com/api/v1'

        logger.info(f"WAN: Starting video generation for {len(scene_image_urls)} scene images using DashScope WAN 2.2...")

        video_urls = [""] * len(scene_image_urls)
        task_data = []

        logger.info("WAN: Phase 1 - Submitting all video generation requests to DashScope...")

        for i, image_url in enumerate(scene_image_urls):
            try:
                if not image_url or i >= len(wan2_5_prompts):
                    logger.warning(f"WAN: Missing image URL or wan2_5_prompt for scene {i+1}")
                    task_data.append(None)
                    continue

                wan2_5_prompt = wan2_5_prompts[i] if wan2_5_prompts[i] else "Animate the static image with subtle movement and UGC-style camera work."

                logger.info(f"WAN: Submitting video request for scene {i+1}...")
                logger.info(f"WAN: Image URL: {image_url}")
                logger.info(f"WAN: WAN 2.2 prompt: {wan2_5_prompt[:100]}...")

                full_prompt = f"{wan2_5_prompt},Engaging, yet natural movement. Subtle camera shifts like organic pans or gentle pushes. Focus on subject's actions with enhanced, but believable energy. Avoid overly cinematic or overly shaky effects. When animating the clean source image, apply the conversion-optimized UGC Low-Fi aesthetic filter. Set the video to achieve a deliberately unpolished, non-cinematic look. Aggressively add High Grain/Noise and enforce Low Contrast, simulating the texture of heavy H.264 social media compression and features mandatory UGC-style captions on screen"

                rsp = await asyncio.to_thread(
                    VideoSynthesis.async_call,
                    api_key=settings.dashscope_api_key,
                    model='wan2.2-i2v-plus',
                    prompt=full_prompt,
                    resolution="1080P",
                    img_url=image_url
                )

                if rsp.status_code == HTTPStatus.OK:
                    task_id = rsp.output.task_id
                    task_data.append({'task_id': task_id, 'response': rsp})
                    logger.info(f"WAN: Scene {i+1} video request submitted successfully, task_id: {task_id}")
                else:
                    logger.error(f"WAN: Failed to submit video request for scene {i+1}: status_code={rsp.status_code}, code={rsp.code}, message={rsp.message}")
                    task_data.append(None)

            except Exception as e:
                logger.error(f"WAN: Failed to submit video request for scene {i+1}: {e}")
                logger.exception(f"WAN: Exception details for scene {i+1}:")
                task_data.append(None)

        successful_submissions = len([t for t in task_data if t])
        logger.info(f"WAN: Submitted {successful_submissions} out of {len(scene_image_urls)} video requests to DashScope")

        logger.info("WAN: Phase 2 - Waiting for all video generation results from DashScope...")

        async def get_video_result(task_info, scene_index):
            """Get result from a single DashScope video generation task"""
            if not task_info:
                return scene_index, ""

            try:
                logger.info(f"WAN: Waiting for scene {scene_index + 1} video result (task_id: {task_info['task_id']})...")

                result = await asyncio.to_thread(VideoSynthesis.wait, task_info['response'])

                if result.status_code == HTTPStatus.OK:
                    video_url = result.output.video_url
                    logger.info(f"WAN: Scene {scene_index + 1} video generated successfully: {video_url}")
                    return scene_index, video_url
                else:
                    logger.error(f"WAN: No video generated for scene {scene_index + 1}: status_code={result.status_code}, code={result.code}, message={result.message}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"WAN: Failed to get video result for scene {scene_index + 1}: {e}")
                logger.exception(f"WAN: Exception details for scene {scene_index + 1}:")
                return scene_index, ""

        tasks = []
        for i, task_info in enumerate(task_data):
            task = get_video_result(task_info, i)
            tasks.append(task)

        logger.info(f"WAN: Waiting for {len(tasks)} video generation tasks to complete...")
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=1800
            )

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"WAN: Video generation task failed: {result}")
                    continue

                scene_index, video_url = result
                video_urls[scene_index] = video_url

        except asyncio.TimeoutError:
            logger.error("WAN: Video generation timed out after 30 minutes")

        successful_videos = len([url for url in video_urls if url])
        logger.info(f"WAN: Generated {successful_videos} out of {len(scene_image_urls)} videos successfully using DashScope WAN 2.2")

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
