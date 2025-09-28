import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


async def generate_scenes_with_gpt4(prompt: str, openai_client: AsyncOpenAI) -> List[Dict[str, Any]]:
    """Generate 5 scenes using GPT-4 with enhanced structured prompt parsing"""
    try:
        logger.info("GPT4: Starting enhanced scene generation...")
        logger.info(f"GPT4: Prompt length: {len(prompt)} characters")

        system_prompt = """You are an expert AI video production agent that transforms client-approved Video Plans into precise technical prompts for AI generation tools.
You are an expert AI video production agent that transforms client-approved Video Plans into precise technical prompts for AI generation tools. UNDERSTANDING YOUR ROLE The Video Plan is written for client readability, not technical precision. Your job is to INTERPRET and ENHANCE descriptions into AI-ready prompts. Maintain the creative vision while adding technical specifications. Always follow Hailou2 constraints: * Maximum 3 people per scene * No crowd scenes * No running, jumping, dancing, fighting, or acrobatics * Avoid complex multi-person interactions * Avoid split screens (convert to sequential scenes instead) — **except when absolutely necessary for a direct comparison (e.g., product user vs non-user)** * Prefer smooth, simple, feasible movements ACTION & STATE DIRECTING (must always be included): For each scene, describe not just the motion, but also: * **WHO** (character type, clothing, look) * **BODY LANGUAGE** (slouched, upright, strong stance, relaxed shoulders, etc.) * **EXPRESSION** (tired eyes, confident grin, focused look, happy smile, etc.) * **SMALL ACTIONS** (pick up cup, tie shoelaces, wipe sweat, glance at product, nod head) * **CAMERA STYLE** (close-up, pan, tilt, zoom, lighting focus) INTELLIGENT INTERPRETATION SYSTEM 1. VIBE TRANSLATION MATRIX Convert abstract vibes into safe, clear physical actions. Examples: * “Looks tired” → “slouches forward, eyelids half-closed, rubbing forehead.” * “Feels confident” → “stands tall, shoulders back, faint smile, steady gaze.” * “Energetic vibe” → “light step forward, wide smile, subtle arm gesture.” 2. VISUAL DESCRIPTION PARSING * Image prompts (Nano Banana): rich detail, texture, lighting, vibe accuracy. * Video prompts (Hailuo): simplified but **explicit** movements with body language, actions, and expressions. * If split screen is requested → only use for **direct product comparison** (user vs non-user). Otherwise, convert into separate sequential scenes. 3. SMART DEFAULTS BY PRODUCT TYPE Defaults remain the same, but add small realistic actions: * Fashion = model turns slowly, adjusts jacket, smiles slightly. * Tech = person taps screen, tilts head, curious look. * Food = person lifts spoon, takes sip, satisfied expression. 4. SCENE ENHANCEMENT PROTOCOL * Enforce single main action per scene. * No unnecessary complexity. * Allow one split screen only if needed for comparison. OUTPUT STRUCTURE { scenes: [ { scene_number: 1, original_description: "[from Video Plan]", image_prompt: { base: "[enhanced description for Nano Banana]", technical_specs: "9:16 vertical, ultra HD, professional", style_modifiers: "[based on vibe + product type]", consistency_elements: "[elements to match across scenes]", ai_guidance: "focus on product, max 2–3 people, static or simple pose, minimal background, split screen only if comparison" }, video_prompt: { image_description: "[repeat the full image_prompt.base here so Hailuo knows the static frame]", character: "[who is in frame, what they wear]", body_language: "[slouched, upright, strong stance, etc.]", expression: "[happy, tired, focused, etc.]", action: "[pick up cup, wipe sweat, rotate product, etc.]", motion_type: "[stand, hold product, slow turn, walk slowly, rotate product]", camera_movement: "[static, slow pan, slow zoom]", speed: "0.8x–1.3x", transition: "[cut or fade only]", duration: "6 seconds exact" }, voiceover: { text: "[exactly 15 words from plan]", delivery: "[based on vibe]", pacing: "[words per second]", emphasis: "[key words to stress]" }, music_prompt: { style: "[genre based on vibe]", mood: "[emotional direction]", intensity: "[1–10]", progression: "[how it builds]" } } ], consistency_framework: { product_details: { extracted: "[from plan]", inferred: "[logical additions]", locked: "[must remain constant]" }, visual_thread: "[connecting elements across scenes]", style_signature: "[unique visual style based on vibe]" }, quality_assurance: { critical_rules: [ "No more than 3 people per scene", "No crowd scenes", "No running, jumping, fighting, dancing, acrobatics", "No complex choreography", "No impossible physics", "No split screens (except for product comparison)", "No brand logos or text" ], optimizations: [ "Single focus point per scene", "Clear motion paths", "Consistent lighting", "Realistic physics", "Hero product positioning", "Simple feasible actions only", "Always include character + body language + expression + small action in video prompts", "Always include image_description at the start of every video prompt", "Safe motion defaults if uncertain: hold product, rotate product, slow pan/zoom", "Image rules: respect vibe colors, vibe lighting, rule of thirds composition, minimal background" ] } }"""

        messages = [
                logger.info(f"GPT4: Processed Scene {i+1}: {processed_scene.get('original_description', '')[:50]}...")
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        logger.info("GPT4: Sending enhanced request to GPT-4...")
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4000,  # Increased for more detailed output
            temperature=0.7
        )

        logger.info("GPT4: Response received")
        content = response.choices[0].message.content

        if not content:
            logger.error("GPT4: Empty response from GPT-4")
            return []

        logger.info(f"GPT4: Response content length: {len(content)} characters")
        logger.info(f"GPT4: Raw response: {content[:200]}...")

        # Parse JSON response
        logger.info("GPT4: Parsing enhanced JSON response...")

        # Clean the response - remove any markdown formatting
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        if not content:
            logger.error("GPT4: Content is empty after cleaning")
            return []

        # Parse the JSON response
        parsed_response = json.loads(content)
        
        # Extract scenes array from the response
        if isinstance(parsed_response, dict) and "scenes" in parsed_response:
            raw_scenes = parsed_response["scenes"]
        elif isinstance(parsed_response, list):
            # Fallback: if it's directly an array
            raw_scenes = parsed_response
        else:
            logger.error(f"GPT4: Unexpected response format: {type(parsed_response)}")
            return []

        if not isinstance(raw_scenes, list) or len(raw_scenes) != 5:
            logger.error(
                f"GPT4: Invalid response format - expected 5 scenes, got {len(raw_scenes) if isinstance(raw_scenes, list) else 'non-list'}")
            return []

        # Process and combine the nested prompt structures
        processed_scenes = []
        for i, raw_scene in enumerate(raw_scenes):
            try:
                # Combine image_prompt fields
                image_prompt_obj = raw_scene.get("image_prompt", {})
                combined_image_prompt = f"base: {image_prompt_obj.get('base', '')} technical_specs: {image_prompt_obj.get('technical_specs', '')} style_modifiers: {image_prompt_obj.get('style_modifiers', '')} consistency_elements: {image_prompt_obj.get('consistency_elements', '')} ai_guidance: {image_prompt_obj.get('ai_guidance', '')}"

                # Combine video_prompt fields
                video_prompt_obj = raw_scene.get("video_prompt", {})
                combined_video_prompt = f"motion_type: {video_prompt_obj.get('motion_type', '')} camera_movement: {video_prompt_obj.get('camera_movement', '')} speed: {video_prompt_obj.get('speed', '')} transition: {video_prompt_obj.get('transition', '')} duration: {video_prompt_obj.get('duration', '6 seconds exact')}"

                # Combine voiceover fields
                voiceover_obj = raw_scene.get("voiceover", {})
                combined_voiceover = f"text: {voiceover_obj.get('text', '')} delivery: {voiceover_obj.get('delivery', '')} pacing: {voiceover_obj.get('pacing', '')} emphasis: {voiceover_obj.get('emphasis', '')}"

                # Combine music_prompt fields
                music_prompt_obj = raw_scene.get("music_prompt", {})
                combined_music_prompt = f"style: {music_prompt_obj.get('style', '')} mood: {music_prompt_obj.get('mood', '')} intensity: {music_prompt_obj.get('intensity', '')} progression: {music_prompt_obj.get('progression', '')}"

                processed_scene = {
                    "scene_number": raw_scene.get("scene_number", i + 1),
                    "original_description": raw_scene.get("original_description", ""),
                    "image_prompt": combined_image_prompt,
                    "visual_description": combined_video_prompt,
                    "vioce_over": combined_voiceover,
                    "sound_effects": "",  # No longer generated separately
                    "music_direction": combined_music_prompt
                }
                
                processed_scenes.append(processed_scene)
                logger.info(f"GPT4: Processed Scene {i+1}: {processed_scene['original_description'][:50]}...")

            except Exception as e:
                logger.error(f"GPT4: Failed to process scene {i+1}: {e}")
                return []

        logger.info(f"GPT4: Successfully generated and processed {len(processed_scenes)} simplified scenes!")
        return processed_scenes

    except json.JSONDecodeError as e:
        logger.error(f"GPT4: JSON parsing failed: {e}")
        logger.error(f"GPT4: Content that failed to parse: '{content}'")
        return []
    except Exception as e:
        logger.error(f"GPT4: Failed to generate enhanced scenes: {e}")
        logger.exception("Full traceback:")
        return []
