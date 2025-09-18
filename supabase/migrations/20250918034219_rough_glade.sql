/*
  # Create music table for background music storage

  1. New Tables
    - `music`
      - `id` (uuid, primary key)
      - `user_id` (text, user identifier from webhook)
      - `video_id` (text, video identifier from webhook)
      - `music_url` (text, normalized background music URL)
      - `created_at` (timestamp)
      - `updated_at` (timestamp)

  2. Security
    - Enable RLS on `music` table
    - Add policy for authenticated users to read their own music
    - Add policy for service role to manage all music

  3. Indexes
    - Index on user_id for fast user queries
    - Index on video_id for fast video queries
    - Composite index on (user_id, video_id) for efficient filtering
    - Unique constraint to prevent duplicate music for same video
*/

CREATE TABLE IF NOT EXISTS music (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL,
  video_id text NOT NULL,
  music_url text NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE music ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY "Users can read their own music"
  ON music
  FOR SELECT
  TO authenticated
  USING (auth.uid()::text = user_id);

CREATE POLICY "Users can insert their own music"
  ON music
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can update their own music"
  ON music
  FOR UPDATE
  TO authenticated
  USING (auth.uid()::text = user_id)
  WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can delete their own music"
  ON music
  FOR DELETE
  TO authenticated
  USING (auth.uid()::text = user_id);

-- Service role policies (for backend processing)
CREATE POLICY "Service role can manage all music"
  ON music
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_music_user_id ON music(user_id);
CREATE INDEX IF NOT EXISTS idx_music_video_id ON music(video_id);
CREATE INDEX IF NOT EXISTS idx_music_user_video ON music(user_id, video_id);
CREATE INDEX IF NOT EXISTS idx_music_created_at ON music(created_at);

-- Create unique constraint to prevent duplicate music for same video
CREATE UNIQUE INDEX IF NOT EXISTS idx_music_video_unique
  ON music(video_id);