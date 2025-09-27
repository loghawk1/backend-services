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
                "image_prompt": scene.get("image_prompt", ""),
                "visual_description": scene.get("visual_description", ""),
                "vioce_over": scene.get("vioce_over", ""),  # Fixed: use correct field name
                "sound_effects": scene.get("sound_effects", ""),
                "music_direction": scene.get("music_direction", "")
            }
            scenes_for_ai.append(scene_data)
            logger.info(f"REVISION_AI: Original Scene {scene_data['scene_number']}: {scene_data['visual_description'][:50]}...")

        system_prompt = """You are an expert AI video revision specialist that processes user revision requests with surgical precision.

CRITICAL DATABASE FIELD MAPPING:
- image_prompt: Combined image generation prompt
- visual_description: Video motion and visual elements
- voiceover: Spoken dialogue/narration text
- vioce_over: Spoken dialogue/narration text
- sound_effects: Audio effects and ambient sounds
- music_direction: Background music style and mood

REVISION ANALYSIS PROTOCOL:

1. PARSE USER INTENT with extreme precision:
   - "movement", "motion", "action", "camera" → ONLY visual_description
   - "background", "lighting", "scene", "visual" → ONLY visual_description + image_prompt
   - "dialogue", "speech", "narration", "voice", "says" → ONLY vioce_over
   - "music", "soundtrack", "background music" → ONLY music_direction
   - "sound", "audio effects", "ambient" → ONLY sound_effects
   - Scene numbers (1-5) → Target ONLY that specific scene
   - "all scenes", "entire video", "everything" → Apply to ALL scenes

2. FIELD PRESERVATION RULE:
   - If a field is NOT mentioned in the revision request → Return EXACT original value
   - If a field IS mentioned → Update according to user's specific request
   - NEVER make assumptions or "helpful" changes to unmentioned fields

3. SMART CONTENT MATCHING:
   - When user describes content without scene numbers, search ALL scenes
   - Match user descriptions to existing visual_description or voiceover content
   - Example: "the woman walking" should find scene with woman walking in visual_description

4. CHANGE SCOPE DETECTION:
   - SPECIFIC: "change scene 3's background" → Only scene 3, only visual_description + image_prompt
   - GLOBAL: "make the music more dramatic" → All 5 scenes, only music_direction
   - TARGETED: "the woman should say something different" → Find scene with woman, update ONLY vioce_over

FORBIDDEN BEHAVIORS:
- NEVER change unmentioned fields "for consistency"
- NEVER make "improvements" not requested by user
- NEVER assume related changes (e.g., changing music when user asks for visual changes)
- NEVER modify scene_number values

OUTPUT REQUIREMENTS:
- Always return exactly 5 scenes
- Always include all 5 fields for each scene: image_prompt, visual_description, voiceover, sound_effects, music_direction
- Always include all 5 fields for each scene: image_prompt, visual_description, vioce_over, sound_effects, music_direction
- Preserve original values for unchanged fields EXACTLY (no paraphrasing)
- Only modify fields explicitly or implicitly targeted by the revision request

EXAMPLE MAPPINGS:
- "make the character move slower" → Find scene with character movement, update ONLY visual_description
- "change the background music to jazz" → Update ONLY music_direction in ALL 5 scenes
- "the woman should say something different" → Find scene with woman, update ONLY voiceover
- "the woman should say something different" → Find scene with woman, update ONLY vioce_over
- "add more lighting to scene 2" → Scene 2 only, update ONLY visual_description + image_prompt
- "remove the sound effects" → Update ONLY sound_effects in ALL 5 scenes to empty or minimal

Output format (JSON only, no explanations or markdown):
{
  "scenes": [
    {
      "scene_number": 1,
      "image_prompt": "...",
      "visual_description": "...",
     "vioce_over": "...",
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

INSTRUCTIONS:
1. Analyze the revision request with surgical precision
2. Identify EXACTLY which fields need changes based on the request
3. For unchanged fields, return the EXACT original values (no paraphrasing)
4. For changed fields, implement the user's specific request
5. Return complete JSON with all 5 scenes and all 5 fields per scene"""

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
            required_fields = ["scene_number", "image_prompt", "visual_description", "vioce_over", "sound_effects", "music_direction"]
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
