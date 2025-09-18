/*
  # Add voiceover_url column to scenes table

  1. Schema Changes
    - Add `voiceover_url` column to store generated voiceover audio URLs
    - Column is optional (nullable) to handle cases where voiceover generation fails

  2. Notes
    - This column will store the audio URL returned from fal.ai ElevenLabs TTS
    - Each scene row will be updated with its corresponding voiceover URL after generation
    - Matches scene_number with voiceover generation order (scene 1 -> voiceover 1, etc.)
*/

-- Add voiceover_url column to scenes table
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'scenes' AND column_name = 'voiceover_url'
  ) THEN
    ALTER TABLE scenes ADD COLUMN voiceover_url text;
  END IF;
END $$;