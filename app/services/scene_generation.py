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

        system_prompt = """You are an expert AI video production agent that transforms client-approved Video Plans into simple technical prompts for AI generation tools.

UNDERSTANDING YOUR ROLE
- The Video Plan is written for client readability, not technical precision.
- Your job is to INTERPRET and ENHANCE descriptions into AI-ready prompts.
- Keep outputs simple and deterministic — make the image prompt clear for Nano Banana and the video prompt a short, unambiguous instruction for Hailou2.

GENERAL RULES
- Maximum 3 people per scene.
- No crowd scenes.
- No running, jumping, dancing, fighting, or acrobatics.
- Avoid complex multi-person interactions.
- Split screens are forbidden except when absolutely necessary for a direct product comparison (user vs non-user). If used, keep it only one split screen in the whole spot and clearly mark it as a comparison.
- One clear simple action per scene. Keep motions obvious and physically feasible.
- Always repeat the image description back to the video generator so it knows exactly what it is animating.

OUTPUT STRUCTURE (Simple)
{
  "scenes": [
    {
      "scene_number": 1,
      "original_description": "<from Video Plan>",
      "image_prompt": {
        "base": "<clear single-sentence description for Nano Banana - what should be generated (objects, people, setting)>",
        "technical_specs": "9:16 vertical, ultra HD, professional",
        "style_modifiers": "<vibe keywords, e.g., bold, clean, vibrant>",
        "consistency_elements": "<product details that must remain identical across scenes>",
        "ai_guidance": "single focus, minimal background, no text overlay, max 3 people"
      },
      "video_prompt": {
        "image_description": "<repeat the full image_prompt.base here exactly as a single sentence so Hailou2 knows the static frame>",
        "your_role": "<simple instruction of what to do with that image, imperative voice. Examples: 'Make the confetti and the shoes burst into the screen, then settle in place.' or 'Make the person look tired: slight slouch, head down, slowly lift cup to mouth....'>",
        "duration": "<optional: duration if necessary, e.g., '6 seconds exact'>"
      },
      "voiceover": {
        "text": "<short voice line from the plan — keep it concise (preferably <=15 words)>",
        "delivery": "<short delivery note, e.g., 'calm, confident' or 'energetic, urgent'>"
      },
      "music_prompt": {
        "style": "<short genre or instrumentation, e.g., 'upbeat electronic' or 'soft piano'>",
        "mood": "<one-word mood, e.g., 'uplifting', 'energetic', 'sophisticated'>",
        "intensity": "<1-10 - how present/intense the track should be>"
      }
    }
  ],
  "consistency_framework": {
    "product_details": {
      "extracted": "<from plan>",
      "inferred": "<logical additions>",
      "locked": "<must remain constant across scenes>"
    },
    "visual_thread": "<single-phrase visual connector across scenes, e.g., 'neon color palette and spotlight on product'>"
  },
  "quality_assurance": {
    "critical_rules": [
      "No more than 3 people per scene",
      "No crowd scenes",
      "No running, jumping, fighting, dancing, acrobatics",
      "No complex choreography",
      "No impossible physics",
      "Only one split screen allowed and only for product comparison",
      "No brand logos or text overlays in image prompts"
    ],
    "optimizations": [
      "Single focus point per scene",
      "Simple, explicit actions only",
      "Always include image_description at top of video_prompt",
      "Keep voiceover short and clear",
      "Keep music prompt concise"
    ]
  }
}"""

        messages = [
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

                # Combine video_prompt fields - only use your_role for visual_description
                video_prompt_obj = raw_scene.get("video_prompt", {})
                combined_video_prompt = video_prompt_obj.get('your_role', '')

                # Combine voiceover fields
                voiceover_obj = raw_scene.get("voiceover", {})
                combined_voiceover = f"text: {voiceover_obj.get('text', '')} delivery: {voiceover_obj.get('delivery', '')}"
                
                # Debug logging for voiceover content
                logger.info(f"GPT4: Scene {i+1} voiceover object: {voiceover_obj}")
                logger.info(f"GPT4: Scene {i+1} combined voiceover: {combined_voiceover}")

                # Combine music_prompt fields
                music_prompt_obj = raw_scene.get("music_prompt", {})
                combined_music_prompt = f"style: {music_prompt_obj.get('style', '')} mood: {music_prompt_obj.get('mood', '')} intensity: {music_prompt_obj.get('intensity', '')} progression: {music_prompt_obj.get('progression', '')}"

                processed_scene = {
                    "scene_number": raw_scene.get("scene_number", i + 1),
                    "original_description": raw_scene.get("original_description", ""),
                    "image_prompt": combined_image_prompt,
                    "visual_description": combined_video_prompt,
                    "vioce_over": combined_voiceover,  # Keep the typo to match database field
                    "sound_effects": "",  # No longer generated separately
                    "music_direction": combined_music_prompt
                }
                
                processed_scenes.append(processed_scene)
                logger.info(f"GPT4: Processed Scene {i+1}: {processed_scene['original_description'][:50]}...")
                logger.info(f"GPT4: Scene {i+1} final vioce_over field: {processed_scene['vioce_over']}")

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


async def wan_scene_generator(prompt: str, openai_client: AsyncOpenAI) -> List[Dict[str, Any]]:
    """Generate 6 WAN scenes using GPT-4 with the specific WAN system prompt"""
    try:
        logger.info("WAN_GPT4: Starting WAN scene generation...")
        logger.info(f"WAN_GPT4: Prompt length: {len(prompt)} characters")

        system_prompt = """You are the Backend Prompt Architect Agent for a UGC video production system. Your job is to take a structured storyboard text (with 6 scenes, each containing “You See” and “You Hear”) and convert it into a backend-ready JSON prompt file for three production engines: * **Nano Banana** → Image Generation * **ElevenLabs** → Voice Generation * **Wan 2.5** → Video Animation --- ### CRITICAL REQUIREMENTS 1. Output **must always be valid JSON**. 2. The JSON object must include: * A "scenes" array with exactly **6 scene objects**. * Each scene object must contain: * "scene_number" → Integer (1–6) * "nano_banana_prompt" → Detailed **visual description** based on *You See* * "elevenlabs_prompt" → Clean **spoken script** extracted from the *Voiceover (VO)* * "eleven_labs_emotion" → Exactly **one** emotion word from: ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral"] you must only select from theses * "eleven_labs_voice_id" → Must be the same **one choice** across all scenes, selected from: ["Deep_Voice_Man", "Wise_Woman"] * "wan2_5_prompt" → Combined **visual + audio action description**, merging *You See* + *Sound Effects (SFX)*. * A "music_prompt" field outside of "scenes", which must be a **concise instrumental mood description under 50 characters** (e.g., "uplifting acoustic pop", "soft lo-fi beats", "warm cinematic piano"). 3. Do not add commentary, explanation, or extra fields—only output JSON. 4. The same "eleven_labs_voice_id" must be used consistently in all six scenes. 5. Preserve the emotional and narrative progression of the storyboard (problem → discovery → solution → transformation → trust → CTA). --- ### OUTPUT TEMPLATE
json
{
 "scenes": [
   {
     "scene_number": 1,
     "nano_banana_prompt": "...",
     "elevenlabs_prompt": "...",
     "eleven_labs_emotion": "...",
     "eleven_labs_voice_id": "Wise_Woman",
     "wan2_5_prompt": "..."
   },
   {
     "scene_number": 2,
     "nano_banana_prompt": "...",
     "elevenlabs_prompt": "...",
     "eleven_labs_emotion": "...",
     "eleven_labs_voice_id": "Wise_Woman",
     "wan2_5_prompt": "..."
   }
   ... scenes 3–6 ...
 ],
 "music_prompt": "..."
}
NOTE: all text overlays should be only on the wan2_5_prompt prompt
Always follow this structure with no deviations."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        logger.info("WAN_GPT4: Sending WAN request to GPT-4...")
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=4000,
            temperature=0.7
        )

        logger.info("WAN_GPT4: Response received")
        content = response.choices[0].message.content

        if not content:
            logger.error("WAN_GPT4: Empty response from GPT-4")
            return [], ""

        logger.info(f"WAN_GPT4: Response content length: {len(content)} characters")
        logger.info(f"WAN_GPT4: Raw response preview: {content[:200]}...")
        logger.info(f"WAN_GPT4: Full raw response from GPT-4:")
        logger.info(f"WAN_GPT4: {content}")

        # Parse JSON response
        logger.info("WAN_GPT4: Parsing WAN JSON response...")

        # Clean the response - remove any markdown formatting
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        if not content:
            logger.error("WAN_GPT4: Content is empty after cleaning")
            return [], ""

        # Parse the JSON response
        try:
            parsed_response = json.loads(content)
            logger.info(f"WAN_GPT4: Parsed response type: {type(parsed_response)}")
            logger.info(f"WAN_GPT4: Parsed response keys: {list(parsed_response.keys()) if isinstance(parsed_response, dict) else 'Not a dict'}")
        except json.JSONDecodeError as e:
            logger.error(f"WAN_GPT4: JSON parsing failed: {e}")
            logger.error(f"WAN_GPT4: Content that failed to parse: '{content}'")
            return [], ""
        
        # Handle both array and object with scenes array + music_prompt
        wan_scenes = []
        music_prompt = ""
        
        if isinstance(parsed_response, list):
            logger.info("WAN_GPT4: Response is array format - extracting scenes only")
            wan_scenes = parsed_response
            logger.warning("WAN_GPT4: Response is array format - no music_prompt field available")
        elif isinstance(parsed_response, dict):
            logger.info("WAN_GPT4: Response is dictionary format - extracting scenes and music_prompt")
            
            # Extract scenes
            if "scenes" in parsed_response:
                wan_scenes = parsed_response["scenes"]
                logger.info(f"WAN_GPT4: Extracted {len(wan_scenes) if isinstance(wan_scenes, list) else 'non-list'} scenes from 'scenes' key")
            else:
                logger.error("WAN_GPT4: No 'scenes' key found in dictionary response")
                logger.error(f"WAN_GPT4: Available keys: {list(parsed_response.keys())}")
                return [], ""
            
            # Extract music_prompt
            if "music_prompt" in parsed_response:
                music_prompt = parsed_response["music_prompt"]
                if music_prompt and music_prompt.strip():
                    logger.info(f"WAN_GPT4: Successfully extracted music prompt: {music_prompt[:100]}...")
                else:
                    logger.warning("WAN_GPT4: music_prompt key found but value is empty")
                    music_prompt = ""
            else:
                logger.warning("WAN_GPT4: No 'music_prompt' key found in dictionary response")
                logger.warning(f"WAN_GPT4: Available keys: {list(parsed_response.keys())}")
                # Set a default music prompt if none provided
                music_prompt = "Lo-fi hip hop with calm steady beat"
                logger.info("WAN_GPT4: Using default music prompt since none was extracted")
        else:
            logger.error(f"WAN_GPT4: Unexpected response format: {type(parsed_response)}")
            logger.error(f"WAN_GPT4: Response content: {parsed_response}")
            return [], ""

        # Validate scenes
        if not isinstance(wan_scenes, list):
            logger.error(f"WAN_GPT4: wan_scenes is not a list, got: {type(wan_scenes)}")
            return [], music_prompt  # Still return music_prompt if extracted
        
        if len(wan_scenes) != 6:
            logger.error(
                f"WAN_GPT4: Invalid scene count - expected 6 scenes, got {len(wan_scenes)}")
            return [], music_prompt  # Still return music_prompt if extracted

        # Validate each scene has required fields
        for i, scene in enumerate(wan_scenes):
            required_fields = ["scene_number", "nano_banana_prompt", "elevenlabs_prompt", "eleven_labs_emotion", "eleven_labs_voice_id", "wan2_5_prompt"]
            for field in required_fields:
                if field not in scene:
                    logger.error(f"WAN_GPT4: Scene {i+1} missing required field: {field}")
                    return [], music_prompt  # Still return music_prompt if extracted
        
        # Add fallback values for missing or empty fields
        for i, scene in enumerate(wan_scenes):
            # Ensure elevenlabs_prompt is never empty
            if not scene.get("elevenlabs_prompt", "").strip():
                default_text = f"Scene {i+1} voiceover text."
                scene["elevenlabs_prompt"] = default_text
                logger.warning(f"WAN_GPT4: Scene {i+1} had empty elevenlabs_prompt, using default: '{default_text}'")
            
            # Ensure eleven_labs_emotion is from allowed set
            allowed_emotions = ["happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral"]
            emotion = scene.get("eleven_labs_emotion", "").strip().lower()
            if not emotion or emotion not in allowed_emotions:
                scene["eleven_labs_emotion"] = "neutral"
                logger.warning(f"WAN_GPT4: Scene {i+1} had invalid emotion '{emotion}', using default: 'neutral'")
            
            # Ensure eleven_labs_voice_id is from allowed set
            allowed_voices = ["Wise_Woman", "Friendly_Person", "Inspirational_girl", "Deep_Voice_Man", "Calm_Woman", 
                            "Casual_Guy", "Lively_Girl", "Patient_Man", "Young_Knight", "Determined_Man", "Lovely_Girl", 
                            "Decent_Boy", "Imposing_Manner", "Elegant_Man", "Abbess", "Sweet_Girl_2", "Exuberant_Girl"]
            voice_id = scene.get("eleven_labs_voice_id", "").strip()
            if not voice_id or voice_id not in allowed_voices:
                scene["eleven_labs_voice_id"] = "Friendly_Person"
                logger.warning(f"WAN_GPT4: Scene {i+1} had invalid voice_id '{voice_id}', using default: 'Friendly_Person'")

        logger.info(f"WAN_GPT4: Successfully generated {len(wan_scenes)} WAN scenes!")
        for i, scene in enumerate(wan_scenes, 1):
            logger.info(f"WAN_GPT4: Scene {i}: {scene.get('nano_banana_prompt', '')[:50]}...")
            logger.info(f"WAN_GPT4: Scene {i} elevenlabs_prompt: '{scene.get('elevenlabs_prompt', '')}'")
            logger.info(f"WAN_GPT4: Scene {i} emotion: '{scene.get('eleven_labs_emotion', '')}'")
            logger.info(f"WAN_GPT4: Scene {i} voice_id: '{scene.get('eleven_labs_voice_id', '')}'")
        
        if music_prompt:
            logger.info(f"WAN_GPT4: Successfully extracted music prompt: {music_prompt}")
        else:
            logger.warning("WAN_GPT4: No music prompt extracted - this will skip music generation")

        return wan_scenes, music_prompt

    except Exception as e:
        logger.error(f"WAN_GPT4: Failed to generate WAN scenes: {e}")
        logger.exception("Full traceback:")
        return [], ""
