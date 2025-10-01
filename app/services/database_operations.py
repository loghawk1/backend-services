import logging
from datetime import datetime
from typing import List, Dict
from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


async def store_scenes_in_supabase(scenes: List[Dict], video_id: str, user_id: str) -> bool:
    """Store generated scenes in Supabase database - creates 5 or 6 rows depending on workflow"""
    try:
        logger.info(f"DATABASE: Storing {len(scenes)} scenes in Supabase for video: {video_id}")
        logger.info(f"DATABASE: User ID: {user_id}")

        supabase = get_supabase_client()

        # Prepare scene data for insertion - create 5 or 6 rows
        scene_records = []
        for scene in scenes:
            scene_record = {
                "user_id": user_id,
                "video_id": video_id,
                "scene_number": scene.get("scene_number", 1),
                "image_prompt": scene.get("image_prompt", "")[:2000],  # New combined image prompt
                "visual_description": scene.get("visual_description", "")[:1000],  # Limit length
                "vioce_over": scene.get("vioce_over", "")[:1000],  # Fixed: use correct field name
                "sound_effects": scene.get("sound_effects", "")[:500],  # Support both workflows
                "music_direction": scene.get("music_direction", "")[:500],
                "image_url": None,  # Will be updated later when scene images are generated
                "voiceover_url": None,  # Will be updated later when voiceovers are generated
                "scene_clip_url": None,  # Will be updated later when videos are generated
            }
            scene_records.append(scene_record)
            logger.info(f"DATABASE: Scene {scene_record['scene_number']} - Image prompt: {scene_record['image_prompt'][:50]}...")

        # Insert all scenes at once
        logger.info(f"DATABASE: Inserting {len(scene_records)} scene records...")
        result = supabase.table("scenes").insert(scene_records).execute()

        expected_count = len(scenes)
        if result.data and len(result.data) == expected_count:
            logger.info(f"DATABASE: Successfully stored {len(result.data)} scenes in database")
            for record in result.data:
                logger.info(f"DATABASE: Scene {record.get('scene_number')} stored with ID: {record.get('id')}")
            return True
        else:
            logger.error(f"DATABASE: Insert failed - Expected {expected_count} records, got {len(result.data) if result.data else 0}")
            return False

    except Exception as e:
        logger.error(f"DATABASE: Failed to store scenes in Supabase: {e}")
        logger.exception("Full traceback:")
        return False


async def store_wan_scenes_in_supabase(wan_scenes: List[Dict], video_id: str, user_id: str) -> bool:
    """Store WAN generated scenes in Supabase database - creates 6 rows with WAN-specific mapping"""
    try:
        logger.info(f"DATABASE: Storing {len(wan_scenes)} WAN scenes in Supabase for video: {video_id}")
        logger.info(f"DATABASE: User ID: {user_id}")

        supabase = get_supabase_client()

        # Prepare WAN scene data for insertion - create 6 rows
        scene_records = []
        for scene in wan_scenes:
            scene_record = {
                "user_id": user_id,
                "video_id": video_id,
                "scene_number": scene.get("scene_number", 1),
                "image_prompt": scene.get("nano_banana_prompt", "")[:2000],  # Map nano_banana_prompt to image_prompt
                "visual_description": scene.get("wan2_5_prompt", "")[:1000],  # Map wan2_5_prompt to visual_description
                "vioce_over": scene.get("elevenlabs_prompt", "")[:1000],  # Map elevenlabs_prompt to vioce_over
                "sound_effects": "",  # WAN workflow doesn't use separate sound effects
                "music_direction": "",  # WAN workflow doesn't use separate music direction
                "image_url": None,  # Will be updated later when scene images are generated
                "voiceover_url": None,  # Will be updated later when voiceovers are generated
                "scene_clip_url": None,  # Will be updated later when videos are generated
            }
            scene_records.append(scene_record)
            logger.info(f"DATABASE: WAN Scene {scene_record['scene_number']} - Nano Banana prompt: {scene_record['image_prompt'][:50]}...")

        # Insert all 6 WAN scenes at once
        logger.info(f"DATABASE: Inserting {len(scene_records)} WAN scene records...")
        result = supabase.table("scenes").insert(scene_records).execute()

        if result.data and len(result.data) == 6:
            logger.info(f"DATABASE: Successfully stored {len(result.data)} WAN scenes in database")
            for record in result.data:
                logger.info(f"DATABASE: WAN Scene {record.get('scene_number')} stored with ID: {record.get('id')}")
            return True
        else:
            logger.error(f"DATABASE: WAN insert failed - Expected 6 records, got {len(result.data) if result.data else 0}")
            return False

    except Exception as e:
        logger.error(f"DATABASE: Failed to store WAN scenes in Supabase: {e}")
        logger.exception("Full traceback:")
        return False


async def update_scenes_with_image_urls(scene_image_urls: List[str], video_id: str, user_id: str) -> bool:
    """Update the scene rows with their generated image URLs (supports both 5 and 6 scenes)"""
    try:
        logger.info(f"DATABASE: Updating {len(scene_image_urls)} scene image URLs for video: {video_id}")

        supabase = get_supabase_client()

        # Get the existing scenes for this video
        result = supabase.table("scenes").select("id, scene_number").eq("video_id", video_id).eq("user_id",
                                                                                                 user_id).order(
            "scene_number").execute()

        expected_count = len(scene_image_urls)
        if not result.data or len(result.data) != expected_count:
            logger.error(f"DATABASE: Expected {expected_count} scenes, found {len(result.data) if result.data else 0}")
            return False

        # Update each scene with its corresponding image URL
        for i, scene_record in enumerate(result.data):
            if i < len(scene_image_urls) and scene_image_urls[i]:
                scene_id = scene_record["id"]
                scene_number = scene_record["scene_number"]
                image_url = scene_image_urls[i]

                logger.info(f"DATABASE: Updating scene {scene_number} (ID: {scene_id}) with image URL")

                update_result = supabase.table("scenes").update({
                    "image_url": image_url,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", scene_id).execute()

                if update_result.data:
                    logger.info(f"DATABASE: Scene {scene_number} image URL updated successfully")
                else:
                    logger.error(f"DATABASE: Failed to update scene {scene_number} image URL")

        logger.info("DATABASE: All scene image URLs updated successfully")
        return True

    except Exception as e:
        logger.error(f"DATABASE: Failed to update scene image URLs: {e}")
        logger.exception("Full traceback:")
        return False


async def update_scenes_with_video_urls(video_urls: List[str], video_id: str, user_id: str) -> bool:
    """Update the scene rows with their generated video URLs in scene_clip_url column (supports both 5 and 6 scenes)"""
    try:
        logger.info(f"DATABASE: Updating {len(video_urls)} scene video URLs for video: {video_id}")

        supabase = get_supabase_client()

        # Get the existing scenes for this video
        result = supabase.table("scenes").select("id, scene_number").eq("video_id", video_id).eq("user_id",
                                                                                                 user_id).order(
            "scene_number").execute()

        expected_count = len(video_urls)
        if not result.data or len(result.data) != expected_count:
            logger.error(f"DATABASE: Expected {expected_count} scenes, found {len(result.data) if result.data else 0}")
            return False

        # Update each scene with its corresponding video URL
        updated_count = 0
        for i, scene_record in enumerate(result.data):
            if i < len(video_urls) and video_urls[i]:
                scene_id = scene_record["id"]
                scene_number = scene_record["scene_number"]
                video_url = video_urls[i]

                logger.info(
                    f"DATABASE: Updating scene {scene_number} (ID: {scene_id}) with video URL in scene_clip_url")
                logger.info(f"DATABASE: Video URL: {video_url}")

                update_result = supabase.table("scenes").update({
                    "scene_clip_url": video_url,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", scene_id).execute()

                if update_result.data:
                    logger.info(f"DATABASE: Scene {scene_number} scene_clip_url updated successfully")
                    updated_count += 1
                else:
                    logger.error(f"DATABASE: Failed to update scene {scene_number} scene_clip_url")
            else:
                scene_number = scene_record["scene_number"]
                logger.warning(f"DATABASE: No video URL available for scene {scene_number}")

        logger.info(f"DATABASE: Updated {updated_count} out of {expected_count} scene video URLs in scene_clip_url column")
        return updated_count > 0

    except Exception as e:
        logger.error(f"DATABASE: Failed to update scene_clip_url: {e}")
        logger.exception("Full traceback:")
        return False


async def update_scenes_with_voiceover_urls(voiceover_urls: List[str], video_id: str, user_id: str) -> bool:
    """Update the scene rows with their generated voiceover URLs (supports both 5 and 6 scenes)"""
    try:
        logger.info(f"DATABASE: Updating {len(voiceover_urls)} scene voiceover URLs for video: {video_id}")

        supabase = get_supabase_client()

        # Get the existing scenes for this video
        result = supabase.table("scenes").select("id, scene_number").eq("video_id", video_id).eq("user_id",
                                                                                                 user_id).order(
            "scene_number").execute()

        expected_count = len(voiceover_urls)
        if not result.data or len(result.data) != expected_count:
            logger.error(f"DATABASE: Expected {expected_count} scenes, found {len(result.data) if result.data else 0}")
            return False

        # Update each scene with its corresponding voiceover URL
        for i, scene_record in enumerate(result.data):
            if i < len(voiceover_urls) and voiceover_urls[i]:
                scene_id = scene_record["id"]
                scene_number = scene_record["scene_number"]
                voiceover_url = voiceover_urls[i]

                logger.info(f"DATABASE: Updating scene {scene_number} (ID: {scene_id}) with voiceover URL")

                update_result = supabase.table("scenes").update({
                    "voiceover_url": voiceover_url,
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", scene_id).execute()

                if update_result.data:
                    logger.info(f"DATABASE: Scene {scene_number} voiceover URL updated successfully")
                else:
                    logger.error(f"DATABASE: Failed to update scene {scene_number} voiceover URL")

        logger.info("DATABASE: All scene voiceover URLs updated successfully")
        return True

    except Exception as e:
        logger.error(f"DATABASE: Failed to update scene voiceover URLs: {e}")
        logger.exception("Full traceback:")
        return False


async def get_scenes_for_video(video_id: str, user_id: str) -> List[Dict]:
    """Retrieve all scenes for a specific video from the database (5 for regular, 6 for WAN)"""
    try:
        logger.info(f"DATABASE: Retrieving scenes for video: {video_id}, user: {user_id}")

        supabase = get_supabase_client()

        # Get all scenes for this video, ordered by scene_number
        result = supabase.table("scenes").select("*").eq("video_id", video_id).eq("user_id", user_id).order("scene_number").execute()

        if not result.data:
            logger.error(f"DATABASE: No scenes found for video: {video_id}")
            return []

        # Support both regular (5 scenes) and WAN (6 scenes) workflows
        expected_counts = [5, 6]
        if len(result.data) not in expected_counts:
            logger.warning(f"DATABASE: Expected 5 or 6 scenes, found {len(result.data)} for video: {video_id}")

        logger.info(f"DATABASE: Successfully retrieved {len(result.data)} scenes for video: {video_id}")
        for scene in result.data:
            logger.info(f"DATABASE: Scene {scene.get('scene_number')}: {scene.get('visual_description', '')[:50]}...")

        return result.data

    except Exception as e:
        logger.error(f"DATABASE: Failed to retrieve scenes for video {video_id}: {e}")
        logger.exception("Full traceback:")
        return []


async def detect_video_workflow_type(video_id: str, user_id: str) -> str:
    """Detect if a video uses regular (5 scenes) or WAN (6 scenes) workflow"""
    try:
        logger.info(f"DATABASE: Detecting workflow type for video: {video_id}")
        
        supabase = get_supabase_client()
        
        # Count scenes for this video
        result = supabase.table("scenes").select("scene_number").eq("video_id", video_id).eq("user_id", user_id).execute()
        
        if not result.data:
            logger.warning(f"DATABASE: No scenes found for video: {video_id}")
            return "regular"  # Default to regular
        
        scene_count = len(result.data)
        
        if scene_count == 6:
            logger.info(f"DATABASE: Video {video_id} detected as WAN workflow (6 scenes)")
            return "wan"
        elif scene_count == 5:
            logger.info(f"DATABASE: Video {video_id} detected as regular workflow (5 scenes)")
            return "regular"
        else:
            logger.warning(f"DATABASE: Video {video_id} has unexpected scene count: {scene_count}, defaulting to regular")
            return "regular"
            
    except Exception as e:
        logger.error(f"DATABASE: Failed to detect workflow type for video {video_id}: {e}")
        return "regular"  # Default to regular on error
async def get_music_for_video(video_id: str, user_id: str) -> Dict:
    """Retrieve background music record for a specific video from the database"""
    try:
        logger.info(f"DATABASE: Retrieving music for video: {video_id}, user: {user_id}")

        supabase = get_supabase_client()

        # Get music record for this video
        result = supabase.table("music").select("*").eq("video_id", video_id).eq("user_id", user_id).execute()

        if not result.data:
            logger.warning(f"DATABASE: No music found for video: {video_id}")
            return {}

        if len(result.data) > 1:
            logger.warning(f"DATABASE: Multiple music records found for video: {video_id}, using first one")

        music_record = result.data[0]
        logger.info(f"DATABASE: Successfully retrieved music for video: {video_id}")
        logger.info(f"DATABASE: Music URL: {music_record.get('music_url', '')}")

        return music_record

    except Exception as e:
        logger.error(f"DATABASE: Failed to retrieve music for video {video_id}: {e}")
        logger.exception("Full traceback:")
        return {}


async def update_video_id_for_scenes(old_video_id: str, new_video_id: str, user_id: str) -> bool:
    """Update video_id for all scenes from old_video_id to new_video_id"""
    try:
        logger.info(f"DATABASE: Updating video_id for scenes from {old_video_id} to {new_video_id}")

        supabase = get_supabase_client()

        # Update all scenes with the old video_id to use the new video_id
        result = supabase.table("scenes").update({
            "video_id": new_video_id,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("video_id", old_video_id).eq("user_id", user_id).execute()

        if result.data:
            updated_count = len(result.data)
            logger.info(f"DATABASE: Successfully updated video_id for {updated_count} scenes")
            return True
        else:
            logger.error(f"DATABASE: No scenes updated for video_id change from {old_video_id} to {new_video_id}")
            return False

    except Exception as e:
        logger.error(f"DATABASE: Failed to update video_id for scenes: {e}")
        logger.exception("Full traceback:")
        return False


async def update_video_id_for_music(old_video_id: str, new_video_id: str, user_id: str) -> bool:
    """Update video_id for music record from old_video_id to new_video_id"""
    try:
        logger.info(f"DATABASE: Updating video_id for music from {old_video_id} to {new_video_id}")

        supabase = get_supabase_client()

        # Update music record with the old video_id to use the new video_id
        result = supabase.table("music").update({
            "video_id": new_video_id,
        }).eq("video_id", old_video_id).eq("user_id", user_id).execute()

        if result.data:
            logger.info(f"DATABASE: Successfully updated video_id for music record")
            return True
        else:
            logger.warning(f"DATABASE: No music record found to update for video_id change from {old_video_id} to {new_video_id}")
            return False

    except Exception as e:
        logger.error(f"DATABASE: Failed to update video_id for music: {e}")
        logger.exception("Full traceback:")
        return False


async def update_scenes_with_revised_content(revised_scenes: List[Dict], video_id: str, user_id: str) -> bool:
    """Update scenes in database with revised content from AI"""
    try:
        logger.info(f"DATABASE: Updating {len(revised_scenes)} scenes with revised content for video: {video_id}")

        supabase = get_supabase_client()

        # Update each scene with revised content
        for scene in revised_scenes:
            scene_number = scene.get("scene_number", 1)
            
            update_data = {
                "image_prompt": scene.get("image_prompt", "")[:2000],  # New combined image prompt
                "visual_description": scene.get("visual_description", "")[:1000],  # Limit length
                "vioce_over": scene.get("vioce_over", "")[:1000],  # Fixed: use correct field name
                "sound_effects": "",  # No longer generated separately
                "music_direction": scene.get("music_direction", "")[:500],
                "updated_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"DATABASE: Updating scene {scene_number} with revised content...")
            
            result = supabase.table("scenes").update(update_data).eq("video_id", video_id).eq("user_id", user_id).eq("scene_number", scene_number).execute()
            
            if result.data:
                logger.info(f"DATABASE: Scene {scene_number} updated successfully")
            else:
                logger.error(f"DATABASE: Failed to update scene {scene_number}")
                return False

        logger.info("DATABASE: All scenes updated with revised content successfully")
        return True

    except Exception as e:
        logger.error(f"DATABASE: Failed to update scenes with revised content: {e}")
        logger.exception("Full traceback:")
        return False


async def store_music_in_supabase(music_url: str, video_id: str, user_id: str) -> bool:
    """Store or update background music URL in Supabase database"""
    try:
        logger.info(f"DATABASE: Storing music URL in Supabase for video: {video_id}")
        logger.info(f"DATABASE: Music URL: {music_url}")

        supabase = get_supabase_client()

        # Check if music record already exists for this video
        existing_result = supabase.table("music").select("*").eq("video_id", video_id).eq("user_id", user_id).execute()

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
            music_record["created_at"] = datetime.utcnow().isoformat()
            result = supabase.table("music").insert(music_record).execute()

        if result.data:
            logger.info("DATABASE: Successfully stored music URL in database")
            return True
        else:
            logger.error("DATABASE: Failed to store music URL")
            return False

    except Exception as e:
        logger.error(f"DATABASE: Failed to store music in Supabase: {e}")
        logger.exception("Full traceback:")
        return False
