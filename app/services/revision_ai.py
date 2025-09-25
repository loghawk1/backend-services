import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


async def generate_revised_scenes_with_gpt4(
    revision_request: str, 
    original_scenes: List[Dict], 
    openai_client: AsyncOpenAI
) -> List[Dict[str, Any]]:
    """
    Generate revised scenes using GPT-4 based on user revision request and original scenes
    
    Args:
        revision_request: User's natural language revision request
        original_scenes: List of 5 original scene dictionaries from database
        openai_client: OpenAI client instance
        
    Returns:
        List of 5 revised scene dictionaries with updated fields
    """
    try:
        logger.info("REVISION_AI: Starting scene revision with GPT-4...")
        logger.info(f"REVISION_AI: Revision request: {revision_request[:100]}...")
        logger.info(f"REVISION_AI: Processing {len(original_scenes)} original scenes")

        # Prepare original scenes data for GPT-4
        scenes_for_ai = []
        for scene in original_scenes:
            scene_data = {
                "scene_number": scene.get("scene_number", 1),
                "visual_description": scene.get("visual_description", ""),
                "voiceover": scene.get("vioce_over", ""),  # Note: matches your table column name
                "sound_effects": scene.get("sound_effects", ""),
                "music_direction": scene.get("music_direction", "")
            }
            scenes_for_ai.append(scene_data)
            logger.info(f"REVISION_AI: Original Scene {scene_data['scene_number']}: {scene_data['visual_description'][:50]}...")

        system_prompt = """You are an AI assistant that processes video revision requests by updating scene breakdowns.

Your tasks:
1. Analyze the user's revision request carefully.
2. Review the 5 original scenes provided.
3. INTELLIGENTLY identify which scene(s) and fields need updating by:
   - If the user mentions a specific scene number, target that scene
   - If the user describes content without scene numbers (e.g., "the man running", "the woman with the bag"), search through all scenes to find matching visual_description or voiceover content
   - If the user makes global requests (e.g., "change the music", "make it more dramatic"), apply changes to ALL relevant scenes and fields
   - If the user mentions specific elements (e.g., "background", "lighting", "movement"), map these to visual_description changes
   - If the user mentions audio elements (e.g., "music", "sound", "audio"), map these to sound_effects and music_direction changes
   - If the user mentions dialogue or speech (e.g., "what she says", "the voiceover"), map these to voiceover changes
4. Generate a complete JSON structure for all 5 scenes with the requested changes applied.
5. For scenes/fields NOT affected by the revision request, keep their original values exactly as provided.
6. For scenes/fields that ARE affected by the revision request, update them according to the user's intent.

CRITICAL RULES:
- SMART INFERENCE: When users don't specify scene numbers, analyze the content of all scenes to find what they're referring to
- CONTEXT MATCHING: Match user descriptions to existing scene content (e.g., "the running man" should match a scene with running in the visual_description)
- GLOBAL vs SPECIFIC: Distinguish between global changes (affecting all scenes) and specific changes (affecting one scene)
- NATURAL LANGUAGE: Users may use casual language - interpret their intent, not just literal words
- FIELD MAPPING: Automatically map user requests to the correct fields:
  * Visual changes (background, lighting, actions, objects) → visual_description
  * Audio changes (music, sounds, effects) → sound_effects and music_direction  
  * Speech changes (dialogue, narration) → voiceover
- Always return exactly 5 scenes
- Always include all 4 fields for each scene: visual_description, voiceover, sound_effects, music_direction
- If a field is not affected by the revision request, keep its original value EXACTLY
- If a field is affected, update it appropriately while maintaining narrative consistency
- Use descriptive, cinematic language for sound_effects and music_direction
- Keep voiceovers concise and engaging (under 100 characters)
- Make visual descriptions detailed and cinematic
- When making changes, ensure they fit naturally with the overall video narrative and flow

EXAMPLES OF SMART INFERENCE:
- "I don't like the way the man is moving" → Find scene with man in visual_description, update that scene's visual_description
- "Change the music to something dramatic" → Update music_direction in ALL 5 scenes to dramatic style
- "Make the background more luxurious" → Update visual_description in scenes that mention backgrounds
- "The woman should be sitting instead of walking" → Find scene with woman walking, change to sitting in visual_description
Output format (JSON only, no explanations):
{
  "scenes": [
    {
      "scene_number": 1,
      "visual_description": "...",
      "voiceover": "...",
      "sound_effects": "...",
      "music_direction": "..."
    },
    ...
  ]
}"""

        # Prepare the user message with revision request and original scenes
        user_message = f"""REVISION REQUEST: {revision_request}

ORIGINAL SCENES:
{json.dumps(scenes_for_ai, indent=2)}

Please analyze the revision request and update the appropriate scenes/fields while keeping unchanged elements exactly as they are."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        logger.info("REVISION_AI: Sending revision request to GPT-4...")
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=2500,
            temperature=0.7
        )

        logger.info("REVISION_AI: Response received from GPT-4")
        content = response.choices[0].message.content

        if not content:
            logger.error("REVISION_AI: Empty response from GPT-4")
            return []

        logger.info(f"REVISION_AI: Response content length: {len(content)} characters")
        logger.info(f"REVISION_AI: Raw response: {content[:200]}...")

        # Parse JSON response
        logger.info("REVISION_AI: Parsing JSON response...")

        # Clean the response - remove any markdown formatting
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        if not content:
            logger.error("REVISION_AI: Content is empty after cleaning")
            return []

        # Parse the JSON response
        parsed_response = json.loads(content)
        
        # Extract scenes array from the response
        if isinstance(parsed_response, dict) and "scenes" in parsed_response:
            revised_scenes = parsed_response["scenes"]
        elif isinstance(parsed_response, list):
            # Fallback: if it's directly an array
            revised_scenes = parsed_response
        else:
            logger.error(f"REVISION_AI: Unexpected response format: {type(parsed_response)}")
            return []

        if not isinstance(revised_scenes, list) or len(revised_scenes) != 5:
            logger.error(
                f"REVISION_AI: Invalid response format - expected 5 scenes, got {len(revised_scenes) if isinstance(revised_scenes, list) else 'non-list'}")
            return []

        # Validate each scene has required fields
        for i, scene in enumerate(revised_scenes):
            required_fields = ["scene_number", "visual_description", "voiceover", "music_direction"]
            for field in required_fields:
                if field not in scene:
                    logger.error(f"REVISION_AI: Scene {i+1} missing required field: {field}")
                    return []

        logger.info(f"REVISION_AI: Successfully generated {len(revised_scenes)} revised scenes!")
        for i, scene in enumerate(revised_scenes, 1):
            visual_desc = scene.get('visual_description', '')[:50] + "..."
            logger.info(f"REVISION_AI: Revised Scene {i}: {visual_desc}")

        return revised_scenes

    except json.JSONDecodeError as e:
        logger.error(f"REVISION_AI: JSON parsing failed: {e}")
        logger.error(f"REVISION_AI: Content that failed to parse: '{content}'")
        return []
    except Exception as e:
        logger.error(f"REVISION_AI: Failed to generate revised scenes: {e}")
        logger.exception("Full traceback:")
        return []
