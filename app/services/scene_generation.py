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
- **Final scene rule**: The last scene of any ad should include a clear visual cue that the video is ending, such as a subtle fade out or showing the brand/product logo, and the music should gradually fade out.

OUTPUT STRUCTURE (Simple)
{
  scenes: [
    {
      scene_number: <integer>,
      original_description: "<from Video Plan>",
      image_prompt: {
        base: "<clear single-sentence description for Nano Banana - what should be generated (objects, people, setting)>",
        technical_specs: "9:16 vertical, ultra HD, professional",
        style_modifiers: "<vibe keywords, e.g., bold, clean, vibrant>",
        consistency_elements: "<product details that must remain identical across scenes>",
        ai_guidance: "single focus, minimal background, no text overlay, max 3 people"
      },
      video_prompt: {
        image_description: "<repeat the full image_prompt.base here exactly as a single sentence so Hailou2 knows the static frame>",
        your_role: "<very short, simple instruction of what to do with that image — one or two sentences, imperative voice. For example, 'Make the confetti and the shoes burst into the screen, then settle in place.' or 'Make the person look tired: slight slouch, head down, slowly lift cup to mouth.' For final scenes: include brand/logo display or fade-out effect and any subtle finishing motion>",
        duration: "<optional: duration if necessary, e.g., '6 seconds exact'>"
      },
      voiceover: {
        text: "<short voice line from the plan — keep it concise (preferably <=15 words)>",
        delivery: "<short delivery note, e.g., 'calm, confident' or 'energetic, urgent'>"
      },
      music_prompt: {
        style: "<short genre or instrumentation, e.g., 'upbeat electronic' or 'soft piano'>",
        mood: "<one-word mood, e.g., 'uplifting', 'energetic', 'sophisticated'>",
        intensity: "<1-10 - how present/intense the track should be>",
        final_scene_fade: "true if this is the final scene; gradually fade out music"
      }
    }
  ],
  consistency_framework: {
    product_details: {
      extracted: "<from plan>",
      inferred: "<logical additions>",
      locked: "<must remain constant across scenes>"
    },
    visual_thread: "<single-phrase visual connector across scenes, e.g., 'neon color palette and spotlight on product'>"
  },
  quality_assurance: {
    critical_rules: [
      "No more than 3 people per scene",
      "No crowd scenes",
      "No running, jumping, fighting, dancing, acrobatics",
      "No complex choreography",
      "No impossible physics",
      "Only one split screen allowed and only for product comparison",
      "No brand logos or text overlays in image prompts except final scene branding"
    ],
    optimizations: [
      "Single focus point per scene",
      "Simple, explicit actions only",
      "Always include image_description at top of video_prompt",
      "Keep voiceover short and clear",
      "Keep music prompt concise",
      "Final scene should visually and audibly indicate the video is ending"
    ]
  }
}
"""

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
