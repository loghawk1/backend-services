import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


async def generate_scenes_with_gpt4(prompt: str, image_url: str, openai_client: AsyncOpenAI) -> List[Dict[str, Any]]:
    """Generate 5 scenes using GPT-4 with structured prompt parsing"""
    try:
        logger.info("GPT4: Starting scene generation...")
        logger.info(f"GPT4: Prompt length: {len(prompt)} characters")
        logger.info(f"GPT4: Image URL: {image_url}")

        system_prompt = """You are an AI assistant that converts structured user video prompts into a JSON scene breakdown.

Your tasks:
1. Parse the user prompt carefully.
2. Extract exactly 5 scenes from the "SCENE-BY-SCENE BREAKDOWN" section of the prompt.
3. Do not add, invent, or modify the visual or voiceover details. Only use what is explicitly written in the user prompt.
4. For each scene, output:
   - "scene_number": The number of the scene.
   - "visual_description": The visual text provided in the prompt.
   - "voiceover": The voiceover text provided in the prompt.
   - "shot_type": Leave empty string `""` if not specified in the prompt.
   - "sound_effects": Generate based on the visual description. Use descriptive, cinematic, and artistic language. Avoid psychological manipulation terms (e.g., tension, fear, FOMO). Focus on immersive, luxury, creative sound effects.
   - "music_direction": Generate based on the vibe, visual, and voiceover. Always use positive, artistic, and creative language. Avoid brand names. Describe styles in terms of cinematic build-ups, dramatic keys, uplifting progressions, refined accents, premium atmosphere, and emotional impact. Emphasize luxury, exclusivity, aspiration, power, and inspiration.
5. Always output valid JSON in this format:
{
  "scenes": [
    {
      "scene_number": 1,
      "visual_description": "...",
      "voiceover": "...",
      "shot_type": "...",
      "sound_effects": "...",
      "music_direction": "..."
    },
    ...
  ]
}
6. Do not include any explanations, markdown formatting, or extra text — only return the final JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]
            }
        ]

        logger.info("GPT4: Sending request to GPT-4...")
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=2000,
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
        logger.info("GPT4: Parsing JSON response...")

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
            scenes = parsed_response["scenes"]
        elif isinstance(parsed_response, list):
            # Fallback: if it's directly an array
            scenes = parsed_response
        else:
            logger.error(f"GPT4: Unexpected response format: {type(parsed_response)}")
            return []

        if not isinstance(scenes, list) or len(scenes) != 5:
            logger.error(
                f"GPT4: Invalid response format - expected 5 scenes, got {len(scenes) if isinstance(scenes, list) else 'non-list'}")
            logger.error(f"GPT4: Response type: {type(scenes)}")
            logger.error(f"GPT4: Response content: {scenes}")
            return []

        # Validate each scene has required fields
        for i, scene in enumerate(scenes):
            required_fields = ["scene_number", "visual_description", "voiceover", "sound_effects", "music_direction"]
            for field in required_fields:
                if field not in scene:
                    logger.error(f"GPT4: Scene {i + 1} missing required field: {field}")
                    return []

        logger.info(f"GPT4: Successfully generated {len(scenes)} scenes!")
        for i, scene in enumerate(scenes, 1):
            visual_desc = scene.get('visual_description', '')[:50] + "..."
            logger.info(f"GPT4: Scene {i}: {visual_desc}")

        return scenes

    except json.JSONDecodeError as e:
        logger.error(f"GPT4: JSON parsing failed: {e}")
        logger.error(f"GPT4: Content that failed to parse: '{content}'")
        return []
    except Exception as e:
        logger.error(f"GPT4: Failed to generate scenes: {e}")
        logger.exception("Full traceback:")
        return []