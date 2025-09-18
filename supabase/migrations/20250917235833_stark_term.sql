/*
  # Create scenes table for video processing

  1. New Tables
    - `scenes`
      - `id` (uuid, primary key)
      - `user_id` (text, user identifier from webhook)
      - `video_id` (text, video identifier from webhook)
      - `scene_number` (integer, scene number 1-5)
      - `visual_description` (text, scene visual description)
      - `voiceover` (text, scene voiceover content)
      - `sound_effects` (text, scene sound effects description)
      - `music_direction` (text, scene music direction)
      - `image_url` (text, generated scene image URL)
      - `created_at` (timestamp)
      - `updated_at` (timestamp)

  2. Security
    - Enable RLS on `scenes` table
    - Add policy for authenticated users to manage their own scenes
    - Add policy for service role to manage all scenes

  3. Indexes
    - Index on user_id for fast user queries
    - Index on video_id for fast video queries
    - Composite index on (user_id, video_id) for efficient filtering
*/

CREATE TABLE IF NOT EXISTS scenes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL,
  video_id text NOT NULL,
  scene_number integer NOT NULL CHECK (scene_number >= 1 AND scene_number <= 5),
  visual_description text NOT NULL,
  voiceover text NOT NULL,
  sound_effects text NOT NULL DEFAULT '',
  music_direction text NOT NULL DEFAULT '',
  image_url text NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE scenes ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY "Users can read their own scenes"
  ON scenes
  FOR SELECT
  TO authenticated
  USING (auth.uid()::text = user_id);

CREATE POLICY "Users can insert their own scenes"
  ON scenes
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can update their own scenes"
  ON scenes
  FOR UPDATE
  TO authenticated
  USING (auth.uid()::text = user_id)
  WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can delete their own scenes"
  ON scenes
  FOR DELETE
  TO authenticated
  USING (auth.uid()::text = user_id);

-- Service role policies (for backend processing)
CREATE POLICY "Service role can manage all scenes"
  ON scenes
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_scenes_user_id ON scenes(user_id);
CREATE INDEX IF NOT EXISTS idx_scenes_video_id ON scenes(video_id);
CREATE INDEX IF NOT EXISTS idx_scenes_user_video ON scenes(user_id, video_id);
CREATE INDEX IF NOT EXISTS idx_scenes_created_at ON scenes(created_at);

-- Create unique constraint to prevent duplicate scenes for same video
CREATE UNIQUE INDEX IF NOT EXISTS idx_scenes_video_scene_unique
  ON scenes(video_id, scene_number);