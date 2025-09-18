import logging
from datetime import datetime
from typing import List, Dict
from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


async def store_scenes_in_supabase(scenes: List[Dict], video_id: str, user_id: str) -> bool:
    """Store generated scenes in Supabase database - creates 5 rows"""
    try:
        logger.info(f"DATABASE: Storing {len(scenes)} scenes in Supabase for video: {video_id}")
        logger.info(f"DATABASE: User ID: {user_id}")

        supabase = get_supabase_client()

        # Prepare scene data for insertion - create 5 rows
        scene_records = []
        for scene in scenes:
            scene_record = {
                "user_id": user_id,
                "video_id": video_id,
                "scene_number": scene.get("scene_number", 1),
                "visual_description": scene.get("visual_description", "")[:1000],  # Limit length
                "vioce_over": scene.get("voiceover", "")[:1000],  # Note: matches your table column name
                "sound_effects": scene.get("sound_effects", "")[:500],
                "music_direction": scene.get("music_direction", "")[:500],
                "image_url": None,  # Will be updated later when scene images are generated
                "voiceover_url": None,  # Will be updated later when voiceovers are generated
                "scene_clip_url": None,  # Will be updated later when videos are generated
            }
            scene_records.append(scene_record)
            logger.info(
                f"DATABASE: Scene {scene_record['scene_number']} - Visual: {scene_record['visual_description'][:50]}...")

        # Insert all 5 scenes at once
        logger.info(f"DATABASE: Inserting {len(scene_records)} scene records...")
        result = supabase.table("scenes").insert(scene_records).execute()

        if result.data and len(result.data) == 5:
            logger.info(f"DATABASE: Successfully stored {len(result.data)} scenes in database")
            for record in result.data:
                logger.info(f"DATABASE: Scene {record.get('scene_number')} stored with ID: {record.get('id')}")
            return True
        else:
            logger.error(f"DATABASE: Insert failed - Expected 5 records, got {len(result.data) if result.data else 0}")
            return False

    except Exception as e:
        logger.error(f"DATABASE: Failed to store scenes in Supabase: {e}")
        logger.exception("Full traceback:")
        return False


async def update_scenes_with_image_urls(scene_image_urls: List[str], video_id: str, user_id: str) -> bool:
    """Update the 5 scene rows with their generated image URLs"""
    try:
        logger.info(f"DATABASE: Updating {len(scene_image_urls)} scene image URLs for video: {video_id}")

        supabase = get_supabase_client()

        # Get the existing 5 scenes for this video
        result = supabase.table("scenes").select("id, scene_number").eq("video_id", video_id).eq("user_id",
                                                                                                 user_id).order(
            "scene_number").execute()

        if not result.data or len(result.data) != 5:
            logger.error(f"DATABASE: Expected 5 scenes, found {len(result.data) if result.data else 0}")
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
    """Update the 5 scene rows with their generated video URLs in scene_clip_url column"""
    try:
        logger.info(f"DATABASE: Updating {len(video_urls)} scene video URLs for video: {video_id}")

        supabase = get_supabase_client()

        # Get the existing 5 scenes for this video
        result = supabase.table("scenes").select("id, scene_number").eq("video_id", video_id).eq("user_id",
                                                                                                 user_id).order(
            "scene_number").execute()

        if not result.data or len(result.data) != 5:
            logger.error(f"DATABASE: Expected 5 scenes, found {len(result.data) if result.data else 0}")
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

        logger.info(f"DATABASE: Updated {updated_count} out of 5 scene video URLs in scene_clip_url column")
        return updated_count > 0

    except Exception as e:
        logger.error(f"DATABASE: Failed to update scene_clip_url: {e}")
        logger.exception("Full traceback:")
        return False


async def update_scenes_with_voiceover_urls(voiceover_urls: List[str], video_id: str, user_id: str) -> bool:
    """Update the 5 scene rows with their generated voiceover URLs"""
    try:
        logger.info(f"DATABASE: Updating {len(voiceover_urls)} scene voiceover URLs for video: {video_id}")

        supabase = get_supabase_client()

        # Get the existing 5 scenes for this video
        result = supabase.table("scenes").select("id, scene_number").eq("video_id", video_id).eq("user_id",
                                                                                                 user_id).order(
            "scene_number").execute()

        if not result.data or len(result.data) != 5:
            logger.error(f"DATABASE: Expected 5 scenes, found {len(result.data) if result.data else 0}")
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