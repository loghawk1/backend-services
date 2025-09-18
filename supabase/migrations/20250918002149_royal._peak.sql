/*
  # Add scene_clip_url column to scenes table

  1. Schema Changes
    - Add `scene_clip_url` column to store generated video URLs
    - Column is optional (nullable) to handle cases where video generation fails

  2. Notes
    - This column will store the video URL returned from fal.ai Minimax Hailuo
    - Each scene row will be updated with its corresponding video URL after generation
    - Matches scene_number with video generation order (scene 1 -> video 1, etc.)
*/

-- Add scene_clip_url column to scenes table
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'scenes' AND column_name = 'scene_clip_url'
  ) THEN
    ALTER TABLE scenes ADD COLUMN scene_clip_url text;
  END IF;
END $$;