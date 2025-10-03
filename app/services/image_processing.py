import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def generate_scene_images_with_fal(image_prompts: List[str], base_image_url: str, aspect_ratio: str = "9:16") -> List[str]:
    """Generate scene images using fal.ai Gemini edit model based on combined image prompts + existing images"""
    try:
        logger.info(f"FAL: Starting scene image generation for {len(image_prompts)} scenes with aspect ratio {aspect_ratio}...")
        scene_image_urls = []

        for i, image_prompt in enumerate(image_prompts, 1):
            try:
                logger.info(f"FAL: Generating image for scene {i}...")
                logger.info(f"FAL: Image prompt: {image_prompt[:100]}...")
                logger.info(f"FAL: Using aspect ratio: {aspect_ratio}")

                # Submit the request using asyncio.to_thread
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/gemini-25-flash-image/edit",
                    arguments={
                        "prompt": image_prompt,
                        "image_urls": [base_image_url],
                        "num_images": 1,
                        "output_format": "jpeg",
                        "aspect_ratio": aspect_ratio
                    }
                )

                # Wait for result
                logger.info(f"FAL: Waiting for scene {i} image result...")
                result = await asyncio.to_thread(handler.get)

                # Extract image URL
                if result and "images" in result and len(result["images"]) > 0:
                    image_url = result["images"][0]["url"]
                    scene_image_urls.append(image_url)
                    logger.info(f"FAL: Scene {i} image generated: {image_url}")
                else:
                    logger.error(f"FAL: No image generated for scene {i}")
                    scene_image_urls.append("")

            except Exception as e:
                logger.error(f"FAL: Failed to generate image for scene {i}: {e}")
                scene_image_urls.append("")

        logger.info(f"FAL: Generated {len([url for url in scene_image_urls if url])} out of {len(image_prompts)} scene images")
        return scene_image_urls

    except Exception as e:
        logger.error(f"FAL: Failed to generate scene images: {e}")
        logger.exception("Full traceback:")
        return []
