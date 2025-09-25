import asyncio
import logging
from typing import List, Dict
import fal_client

logger = logging.getLogger(__name__)


async def generate_background_music_with_fal(music_prompts: List[str]) -> str:
    """Generate background music using Google's Lyria 2 by combining all scene music prompts"""
    try:
        logger.info(f"FAL: Starting background music generation from {len(music_prompts)} music prompts...")
        logger.info("FAL: This may take several minutes, please wait...")
        
        # Combine all music prompts from all 5 scenes
        combined_music_elements = []
        
        for i, music_prompt in enumerate(music_prompts, 1):
            if music_prompt and music_prompt.strip():
                combined_music_elements.append(music_prompt.strip())
                logger.info(f"FAL: Music prompt {i}: {music_prompt[:50]}...")
            
        if not combined_music_elements:
            logger.warning("FAL: No music directions or sound effects found, using default prompt")
            prompt = "Upbeat commercial background music, energetic and engaging, perfect for product showcase (no words only melody)"
        else:
            # Join all elements with spaces and add the requirement for no vocals
            prompt = " ".join(combined_music_elements) + " (no words only melody)"
        
        logger.info(f"FAL: Combined music prompt: {prompt}")
        logger.info(f"FAL: Prompt length: {len(prompt)} characters")
        
        # Submit music generation request using Google's Lyria 2
        logger.info("FAL: Submitting music generation request to Lyria 2...")
        logger.info(f"FAL: Using prompt: {prompt}")
        
        # Add timeout wrapper for music generation
        try:
            handler = await asyncio.to_thread(
                fal_client.submit,
                "fal-ai/lyria2",
                arguments={
                    "prompt": prompt,
                    "negative_prompt": "vocals, slow tempo, speech, talking, singing, lyrics, words"
                }
            )
            
            logger.info("FAL: Waiting for music generation result (this may take 10-15 minutes)...")
            
            # Add timeout for the result waiting
            result = await asyncio.wait_for(
                asyncio.to_thread(handler.get),
                timeout=900  # 15 minutes timeout for music generation
            )
            
        except asyncio.TimeoutError:
            logger.error("FAL: Music generation timed out after 15 minutes")
            return ""
        except Exception as e:
            logger.error(f"FAL: Music generation request failed: {e}")
            return ""
        
        # Extract music URL from result
        if result and "audio" in result and "url" in result["audio"]:
            raw_music_url = result["audio"]["url"]
            logger.info(f"FAL: Raw background music generated successfully: {raw_music_url}")
            return raw_music_url
        else:
            logger.error("FAL: No music generated")
            logger.debug(f"FAL: Raw result: {result}")
            return ""
    
    except Exception as e:
        logger.error(f"FAL: Failed to generate background music: {e}")
        logger.exception("Full traceback:")
        return ""


async def normalize_music_volume(raw_music_url: str, offset: float = -15.0) -> str:
    """Normalize music volume using fal.ai loudnorm with specified offset"""
    try:
        logger.info(f"FAL: Starting music volume normalization...")
        logger.info(f"FAL: Raw music URL: {raw_music_url}")
        logger.info(f"FAL: Volume offset: {offset}dB")
        
        # Submit loudnorm request
        handler = await asyncio.to_thread(
            fal_client.submit,
            "fal-ai/ffmpeg-api/loudnorm",
            arguments={
                "audio_url": raw_music_url,
                "offset": offset,
                "integrated_loudness": -18,  # Standard loudness target
                "true_peak": -0.1,           # Prevent clipping
                "loudness_range": 7          # Dynamic range
            }
        )
        
        logger.info("FAL: Waiting for loudnorm result...")
        result = await asyncio.to_thread(handler.get)
        
        # Extract normalized audio URL
        if result and "audio" in result and "url" in result["audio"]:
            normalized_music_url = result["audio"]["url"]
            logger.info(f"FAL: Music volume normalized successfully: {normalized_music_url}")
            return normalized_music_url
        else:
            logger.error("FAL: Music normalization failed, returning original URL")
            logger.debug(f"FAL: Raw result: {result}")
            return raw_music_url
    
    except Exception as e:
        logger.error(f"FAL: Failed to normalize music volume: {e}")
        logger.exception("Full traceback:")
        return raw_music_url  # Return original URL as fallback


async def store_music_in_database(music_url: str, video_id: str, user_id: str) -> bool:
    """Store or update the normalized music URL in the music table (upsert operation)"""
    try:
        logger.info(f"DATABASE: Storing background music for video: {video_id}")
        logger.info(f"DATABASE: User ID: {user_id}")
        logger.info(f"DATABASE: Music URL: {music_url}")
        
        from ..supabase_client import get_supabase_client
        from datetime import datetime
        
        supabase = get_supabase_client()
        
        # Check if music record already exists
        existing_result = supabase.table("music").select("id").eq("video_id", video_id).eq("user_id", user_id).execute()
        
        music_record = {
            "user_id": user_id,
            "video_id": video_id,
            "music_url": music_url,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if existing_result.data and len(existing_result.data) > 0:
            # Update existing record
            logger.info("DATABASE: Updating existing music record...")
            # Remove updated_at from update payload to avoid PGRST204 error
            update_record = {
                "user_id": user_id,
                "video_id": video_id,
                "music_url": music_url
                # Let database handle updated_at automatically
            }
            result = supabase.table("music").update(update_record).eq("video_id", video_id).eq("user_id", user_id).execute()
        else:
            # Insert new record
            logger.info("DATABASE: Inserting new music record...")
            # Remove updated_at from insert payload to avoid PGRST204 error
            insert_record = {
                "user_id": user_id,
                "video_id": video_id,
                "music_url": music_url,
                "created_at": datetime.utcnow().isoformat()
                # Let database handle updated_at automatically with DEFAULT now()
            }
            result = supabase.table("music").insert(insert_record).execute()
        
        if result.data:
            logger.info(f"DATABASE: Music upserted successfully with ID: {result.data[0].get('id')}")
            return True
        else:
            logger.error("DATABASE: Failed to upsert music record")
            logger.debug(f"DATABASE: Insert result: {result}")
            return False
    
    except Exception as e:
        logger.error(f"DATABASE: Failed to upsert music: {e}")
        logger.exception("Full traceback:")
        return False
