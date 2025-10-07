# FFmpeg Video Processing API - Usage Guide

## Overview
This project now uses the FFmpeg Video Processing API for all video composition, background music addition, and caption generation tasks. The implementation provides immediate polling, comprehensive error handling, and detailed logging.

## API Configuration

### Environment Variables
```bash
# FFmpeg API Base URL (default: https://fantastic-endurance-production.up.railway.app)
FFMPEG_API_BASE_URL=https://fantastic-endurance-production.up.railway.app

# Optional: API Key for authentication (not currently used)
FFMPEG_API_KEY=
```

## Core Services

### 1. FFmpeg API Client (`app/services/ffmpeg_api_client.py`)

#### Submit Merge Task
Combines multiple scene videos with voiceovers.

```python
from app.services.ffmpeg_api_client import submit_merge_task

task_id = await submit_merge_task(
    scene_clip_urls=["https://example.com/scene1.mp4", "https://example.com/scene2.mp4"],
    voiceover_urls=["https://example.com/voice1.mp3", "https://example.com/voice2.mp3"],
    width=1080,
    height=1920,
    video_volume=0.2,
    voiceover_volume=2.0
)
```

**Parameters:**
- `scene_clip_urls`: List of scene video URLs (must match voiceover count)
- `voiceover_urls`: List of voiceover audio URLs (must match scene count)
- `width`: Output width in pixels (default: 1080, range: 480-3840)
- `height`: Output height in pixels (default: 1920, range: 480-3840)
- `video_volume`: Volume for video audio (default: 0.2, range: 0.0-1.0)
- `voiceover_volume`: Volume for voiceover (default: 2.0, range: 0.0-10.0)

**Returns:** `task_id` (string) or `None` on failure

#### Submit Background Music Task
Adds background music to a video.

```python
from app.services.ffmpeg_api_client import submit_background_music_task

task_id = await submit_background_music_task(
    video_url="https://example.com/video.mp4",
    music_url="https://example.com/music.mp3",
    music_volume=0.3,
    video_volume=1.0
)
```

**Parameters:**
- `video_url`: URL of the video to process
- `music_url`: URL of the background music file
- `music_volume`: Volume for background music (default: 0.3, range: 0.0-1.0)
- `video_volume`: Volume for video audio (default: 1.0, range: 0.0-1.0)

**Returns:** `task_id` (string) or `None` on failure

#### Submit Caption Task
Adds AI-generated subtitles using Whisper.

```python
from app.services.ffmpeg_api_client import submit_caption_task

task_id = await submit_caption_task(
    video_url="https://example.com/video.mp4",
    model_size="small"
)
```

**Parameters:**
- `video_url`: URL of the video to process
- `model_size`: Whisper model size (default: "small")
  - `tiny`: Fastest, least accurate
  - `base`: Fast, good for simple speech
  - `small`: Balanced (recommended)
  - `medium`: Higher accuracy, slower
  - `large`: Best accuracy, slowest

**Returns:** `task_id` (string) or `None` on failure

#### Poll Task Status
Polls task until completion or failure.

```python
from app.services.ffmpeg_api_client import poll_task_status

video_url, error = await poll_task_status(
    task_id="550e8400-e29b-41d4-a716-446655440000",
    poll_interval=5,
    max_wait_time=600
)
```

**Parameters:**
- `task_id`: Task ID from submission
- `poll_interval`: Seconds between checks (default: 5)
- `max_wait_time`: Maximum wait time in seconds (default: 600)

**Returns:** Tuple of `(video_url, error_message)` - one will be `None`

### 2. Polling Service (`app/services/polling_service.py`)

Provides specialized polling functions for different task types.

```python
from app.services.polling_service import (
    poll_merge_task,
    poll_background_music_task,
    poll_caption_task
)

# Poll merge task (10 minute timeout)
video_url = await poll_merge_task(task_id)

# Poll background music task (5 minute timeout)
video_url = await poll_background_music_task(task_id)

# Poll caption task (10 minute timeout)
video_url = await poll_caption_task(task_id)
```

### 3. High-Level Composition Functions

#### Compose WAN Videos with Voiceovers
```python
from app.services.json2video_composition import compose_wan_videos_and_voiceovers_with_ffmpeg

composed_url = await compose_wan_videos_and_voiceovers_with_ffmpeg(
    scene_clip_urls=["url1", "url2", "url3", "url4", "url5", "url6"],
    voiceover_urls=["voice1", "voice2", "voice3", "voice4", "voice5", "voice6"],
    aspect_ratio="9:16"
)
```

#### Add Background Music
```python
from app.services.json2video_composition import compose_final_video_with_music_ffmpeg

final_url = await compose_final_video_with_music_ffmpeg(
    composed_video_url="https://example.com/video.mp4",
    music_url="https://example.com/music.mp3",
    aspect_ratio="9:16"
)
```

#### Add Captions
```python
from app.services.caption_generation import add_captions_to_video

captioned_url = await add_captions_to_video(
    final_video_url="https://example.com/video.mp4",
    aspect_ratio="9:16",
    model_size="small"
)
```

## Task Status Flow

```
SUBMIT → QUEUED → RUNNING → SUCCESS
                            ↘ FAILED
```

1. **Submit**: Task is created and submitted to API
2. **Queued**: Task is waiting in queue
3. **Running**: Task is being processed by worker
4. **Success**: Task completed, video URL available
5. **Failed**: Task failed, error message available

## Processing Times

| Task Type | Typical Duration | Factors |
|-----------|------------------|---------|
| Merge (2 scenes) | 2-5 minutes | Scene count, file sizes |
| Merge (6 scenes) | 5-12 minutes | Scene count, file sizes |
| Background Music | 30 seconds - 2 minutes | Video length |
| Caption (tiny) | 30 sec - 1 min | Video length |
| Caption (small) | 1-3 minutes | Video length |
| Caption (large) | 3-8 minutes | Video length, audio complexity |

## Error Handling

All functions include comprehensive error handling:

```python
try:
    task_id = await submit_merge_task(...)
    if not task_id:
        # Handle submission failure
        logger.error("Failed to submit merge task")
        return None

    video_url = await poll_merge_task(task_id)
    if not video_url:
        # Handle polling failure
        logger.error("Failed to complete merge task")
        return None

    return video_url

except Exception as e:
    logger.error(f"Merge operation failed: {e}")
    return None
```

## Logging

All operations include detailed logging:

```python
# Submission logging
logger.info("FFMPEG_API: Submitting merge task...")
logger.info(f"FFMPEG_API: Scene clips: 6 videos")

# Polling logging
logger.info(f"FFMPEG_API: Status check #5 (elapsed: 25.3s)")
logger.info(f"FFMPEG_API: Status [running]")

# Completion logging
logger.info("FFMPEG_API: Task completed successfully!")
logger.info(f"FFMPEG_API: Duration: 123.5s")
logger.info(f"FFMPEG_API: Video URL: https://...")
```

## Best Practices

### 1. Always Validate URLs
```python
if not video_url or not video_url.startswith("http"):
    logger.error(f"Invalid video URL: {video_url}")
    return None
```

### 2. Handle File Size Limits
- Merge: 100MB per file, 500MB total
- Background Music: 100MB per file, 200MB total
- Caption: 100MB per file

### 3. Choose Appropriate Whisper Model
- Use `tiny` or `base` for testing
- Use `small` for production (good balance)
- Use `medium` or `large` for noisy audio or complex speech

### 4. Set Realistic Timeouts
```python
# Merge tasks: 8-10 minutes
video_url = await poll_merge_task(task_id, max_wait_time=600)

# Background music: 3-5 minutes
video_url = await poll_background_music_task(task_id, max_wait_time=300)

# Captions: 10 minutes (for large models)
video_url = await poll_caption_task(task_id, max_wait_time=600)
```

### 5. Implement Fallbacks
```python
captioned_url = await add_captions_to_video(video_url, aspect_ratio)

# If captioning fails, return original video
if not captioned_url:
    return video_url  # Fallback to original
```

## Integration with Worker Pipeline

The worker automatically uses FFmpeg API for all video processing:

```python
# WAN video composition
final_video_url = await compose_wan_final_video_with_audio(
    video_urls,
    voiceover_urls,
    aspect_ratio
)

# Background music
final_video_with_music = await compose_final_video_with_music_ffmpeg(
    final_video_url,
    normalized_music_url,
    aspect_ratio
)

# Captions
captioned_video_url = await add_captions_to_video(
    final_video_url,
    aspect_ratio,
    model_size="small"
)
```

## Troubleshooting

### Issue: Task submission fails
- Check FFmpeg API is accessible
- Verify all URLs are valid and publicly accessible
- Check file sizes are within limits
- Review logs for specific error messages

### Issue: Task stuck in "queued" status
- Worker may be processing other tasks
- Queue may be backed up
- Check FFmpeg API health endpoint

### Issue: Task fails with timeout
- Increase `max_wait_time` parameter
- Use smaller Whisper model for captions
- Check video file sizes and complexity

### Issue: Video URL not accessible
- Video may have expired (2-hour TTL)
- Download video immediately after completion
- Check URL format is correct

## Testing

### Test Merge Task
```python
import asyncio
from app.services.ffmpeg_api_client import submit_merge_task
from app.services.polling_service import poll_merge_task

async def test_merge():
    task_id = await submit_merge_task(
        scene_clip_urls=["https://example.com/scene1.mp4"],
        voiceover_urls=["https://example.com/voice1.mp3"],
        width=1080,
        height=1920
    )

    if task_id:
        print(f"Task submitted: {task_id}")
        video_url = await poll_merge_task(task_id)
        print(f"Result: {video_url}")

asyncio.run(test_merge())
```

### Test Caption Task
```python
import asyncio
from app.services.caption_generation import add_captions_to_video

async def test_captions():
    result = await add_captions_to_video(
        final_video_url="https://example.com/video.mp4",
        aspect_ratio="9:16",
        model_size="small"
    )
    print(f"Captioned video: {result}")

asyncio.run(test_captions())
```

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Review this usage guide
3. Consult FFMPEG_MIGRATION_SUMMARY.md for architecture details
4. Check FFmpeg API documentation at base URL /docs
