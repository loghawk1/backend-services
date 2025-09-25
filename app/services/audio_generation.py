import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def generate_voiceovers_with_fal(voiceover_prompts: List[str]) -> List[str]:
    """Generate voiceovers for all scenes concurrently using fal.ai ElevenLabs Turbo v2.5"""
    try:
        logger.info(f"FAL: Starting concurrent voiceover generation for {len(voiceover_prompts)} scenes...")
        
        # Initialize results list
        voiceover_urls = [""] * len(voiceover_prompts)
        handlers = []

        # Phase 1: Submit all voiceover requests concurrently
        logger.info("FAL: Phase 1 - Submitting all voiceover requests...")
        
        for i, voiceover_prompt in enumerate(voiceover_prompts, 1):
            try:
                # Extract just the text part from the combined voiceover prompt
                voiceover_text = ""
                if voiceover_prompt and "text:" in voiceover_prompt:
                    # Extract text between "text:" and the next field
                    text_start = voiceover_prompt.find("text:") + 5
                    text_end = voiceover_prompt.find("delivery:", text_start)
                    if text_end == -1:
                        text_end = len(voiceover_prompt)
                    voiceover_text = voiceover_prompt[text_start:text_end].strip()
                
                if not voiceover_text:
                    logger.warning(f"FAL: No voiceover text for scene {i}")
                    handlers.append(None)
                    continue

                logger.info(f"FAL: Submitting voiceover request for scene {i}...")
                logger.info(f"FAL: Text: {voiceover_text[:50]}...")

                # Submit voiceover generation request using the new Turbo v2.5 model
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

                handlers.append(handler)
                logger.info(f"FAL: Scene {i} voiceover request submitted successfully")

            except Exception as e:
                logger.error(f"FAL: Failed to submit voiceover request for scene {i}: {e}")
                handlers.append(None)

        logger.info(f"FAL: Submitted {len([h for h in handlers if h])} out of {len(voiceover_prompts)} voiceover requests")

        # Phase 2: Wait for all results concurrently
        logger.info("FAL: Phase 2 - Waiting for all voiceover generation results...")

        async def get_voiceover_result(handler, scene_index):
            """Get result from a single voiceover generation handler"""
            if not handler:
                return scene_index, ""

            try:
                logger.info(f"FAL: Waiting for scene {scene_index + 1} voiceover result...")
                result = await asyncio.to_thread(handler.get)

                # Extract audio URL from the new response format
                if result and "audio" in result and "url" in result["audio"]:
                    voiceover_url = result["audio"]["url"]
                    logger.info(f"FAL: Scene {scene_index + 1} voiceover generated: {voiceover_url}")
                    return scene_index, voiceover_url
                else:
                    logger.error(f"FAL: No voiceover generated for scene {scene_index + 1}")
                    logger.debug(f"FAL: Raw result: {result}")
                    return scene_index, ""

            except Exception as e:
                logger.error(f"FAL: Failed to get voiceover result for scene {scene_index + 1}: {e}")
                return scene_index, ""

        # Create tasks for all handlers
        tasks = []
        for i, handler in enumerate(handlers):
            task = get_voiceover_result(handler, i)
            tasks.append(task)

        # Wait for all results with timeout
        logger.info(f"FAL: Waiting for {len(tasks)} voiceover generation tasks to complete...")
        try:
            # Add timeout to prevent hanging (voiceovers are much faster than videos)
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=120  # 2 minutes timeout for voiceovers
            )

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"FAL: Voiceover generation task failed: {result}")
                    continue

                scene_index, voiceover_url = result
                voiceover_urls[scene_index] = voiceover_url

        except asyncio.TimeoutError:
            logger.error("FAL: Voiceover generation timed out after 2 minutes")
            # Continue with whatever results we have

        successful_voiceovers = len([url for url in voiceover_urls if url])
        logger.info(f"FAL: Generated {successful_voiceovers} out of {len(voiceover_prompts)} voiceovers successfully")

        # Log final results
        for i, url in enumerate(voiceover_urls):
            if url:
                logger.info(f"FAL: Scene {i+1} final voiceover URL: {url}")
            else:
                logger.warning(f"FAL: Scene {i+1} has no voiceover URL")

        return voiceover_urls

    except Exception as e:
        logger.error(f"FAL: Failed to generate voiceovers: {e}")
        logger.exception("Full traceback:")
        return []
