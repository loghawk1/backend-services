import asyncio
import logging
from typing import Dict
import fal_client

logger = logging.getLogger(__name__)


async def generate_single_voiceover_with_fal(voiceover_text: str) -> str:
    """Generate a single voiceover using fal.ai ElevenLabs Turbo v2.5"""
    try:
        logger.info(f"FAL: Starting single voiceover generation...")
        logger.info(f"FAL: Text: {voiceover_text[:50]}...")

        # Submit voiceover generation request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/elevenlabs/tts/turbo-v2.5",
            arguments={
                "text": voiceover_text,
                "voice": "Rachel",
                "stability": 0.5,
                "similarity_boost": 0.75,
                "speed": 1.0
            }
        )

        logger.info("FAL: Waiting for single voiceover result...")
        result = await asyncio.to_thread(handler.get)

        # Extract audio URL from the response
        if result and "audio" in result and "url" in result["audio"]:
            voiceover_url = result["audio"]["url"]
            logger.info(f"FAL: Single voiceover generated successfully: {voiceover_url}")
            return voiceover_url
        else:
            logger.error("FAL: No voiceover generated")
            logger.debug(f"FAL: Raw result: {result}")
            return ""

    except Exception as e:
        logger.error(f"FAL: Failed to generate single voiceover: {e}")
        logger.exception("Full traceback:")
        return ""


async def generate_single_scene_image_with_fal(visual_description: str, base_image_url: str) -> str:
    """Generate a single scene image using fal.ai Gemini edit model"""
    try:
        logger.info(f"FAL: Starting single scene image generation...")
        logger.info(f"FAL: Visual description: {visual_description[:100]}...")
        logger.info(f"FAL: Base image URL: {base_image_url}")

        # Submit image generation request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/gemini-25-flash-image/edit",
            arguments={
                "prompt": visual_description,
                "image_urls": [base_image_url],
                "num_images": 1,
                "output_format": "jpeg"
            }
        )

        logger.info("FAL: Waiting for single scene image result...")
        result = await asyncio.to_thread(handler.get)

        # Extract image URL
        if result and "images" in result and len(result["images"]) > 0:
            image_url = result["images"][0]["url"]
            logger.info(f"FAL: Single scene image generated successfully: {image_url}")
            return image_url
        else:
            logger.error("FAL: No scene image generated")
            logger.debug(f"FAL: Raw result: {result}")
            return ""

    except Exception as e:
        logger.error(f"FAL: Failed to generate single scene image: {e}")
        logger.exception("Full traceback:")
        return ""


async def generate_single_video_with_fal(image_url: str, visual_description: str) -> str:
    """Generate a single video from scene image using fal.ai MiniMax Hailuo-02"""
    try:
        logger.info(f"FAL: Starting single video generation...")
        logger.info(f"FAL: Image URL: {image_url}")
        logger.info(f"FAL: Visual description: {visual_description[:100]}...")

        # Use visual description as prompt
        prompt = visual_description if visual_description else "Create a dynamic product showcase video from this image. Add smooth camera movements and professional lighting effects."

        # Submit video generation request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/minimax/hailuo-02/standard/image-to-video",
            arguments={
                "prompt": prompt,
                "image_url": image_url,
                "duration": "6",            # 6 seconds
                "prompt_optimizer": True,   # keep true for better results
                "resolution": "768P"        # default high resolution
            }
        )

        logger.info("FAL: Waiting for single video result...")
        result = await asyncio.to_thread(handler.get)

        if result and "video" in result and "url" in result["video"]:
            video_url = result["video"]["url"]
            logger.info(f"FAL: Single video generated successfully: {video_url}")
            return video_url
        else:
            logger.error("FAL: No video generated")
            logger.debug(f"FAL: Raw result: {result}")
            return ""

    except Exception as e:
        logger.error(f"FAL: Failed to generate single video: {e}")
        logger.exception("Full traceback:")
        return ""
