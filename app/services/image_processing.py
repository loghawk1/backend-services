import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def resize_image_with_fal(image_url: str) -> str:
    """
    Resize/reframe image using fal.ai Luma Photon Reframe API.
    Uses fal_client (sync) inside async with asyncio.to_thread.
    """
    try:
        logger.info("FAL: Starting image resize/reframe...")
        logger.info(f"FAL: Original image URL: {image_url}")

        # Submit the request (runs in thread to not block event loop)
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/luma-photon/reframe",
            arguments={
                "image_url": image_url,
                "aspect_ratio": "9:16",
                "prompt": (
                    "Resize this image to a 9:16 aspect ratio. Automatically detect the background "
                    "and extend it seamlessly to fill the extra space, keeping the subject untouched. "
                    "Do not stretch or distort the subject, only expand the natural background so the "
                    "final image looks natural and consistent."
                ),
            },
        )

        # Wait for result (blocking get wrapped in thread)
        logger.info("FAL: Waiting for image processing result...")
        result = await asyncio.to_thread(handler.get)

        logger.debug(f"FAL: Raw result: {result}")

        # Handle both "image" and "images"
        if result:
            if "image" in result and "url" in result["image"]:
                resized_image_url = result["image"]["url"]
                logger.info(f"FAL: Image resized successfully: {resized_image_url}")
                return resized_image_url

            elif "images" in result and isinstance(result["images"], list) and len(result["images"]) > 0:
                resized_image_url = result["images"][0].get("url", image_url)
                logger.info(f"FAL: Image resized successfully: {resized_image_url}")
                return resized_image_url

        logger.error("FAL: No valid URL in result, using original")
        return image_url

    except Exception as e:
        logger.error(f"FAL: Failed to resize image: {e}")
        logger.exception("Full traceback:")
        return image_url


async def generate_scene_images_with_fal(scenes: List[Dict]) -> List[str]:
    """Generate scene images using fal.ai Gemini edit model based on visual descriptions + existing images"""
    try:
        logger.info(f"FAL: Starting scene image generation for {len(scenes)} scenes...")
        scene_image_urls = []

        for i, scene in enumerate(scenes, 1):
            try:
                visual_description = scene.get("visual_description", "")
                image_urls = scene.get("image_urls", [])  # Expecting input scenes to have this field
                logger.info(f"FAL: Generating image for scene {i}...")
                logger.info(f"FAL: Visual description: {visual_description[:100]}...")

                # Submit the request using asyncio.to_thread
                handler = await asyncio.to_thread(
                    fal_client.submit,
                    "fal-ai/gemini-25-flash-image/edit",
                    arguments={
                        "prompt": visual_description,
                        "image_urls": image_urls,
                        "num_images": 1,
                        "output_format": "jpeg"
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

        logger.info(f"FAL: Generated {len([url for url in scene_image_urls if url])} out of {len(scenes)} scene images")
        return scene_image_urls

    except Exception as e:
        logger.error(f"FAL: Failed to generate scene images: {e}")
        logger.exception("Full traceback:")
        return []