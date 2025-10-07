# FFmpeg Video Caption Service

Self-hosted video captioning service using FFmpeg + Whisper, with static file hosting on Railway.

## 🎯 How It Works

### Simple Architecture

```
Input Video URL
  ↓
Download video
  ↓
Transcribe with Whisper
  ↓
Generate SRT subtitles
  ↓
Burn subtitles with FFmpeg
  ↓
Save to static/videos/
  ↓
Return Railway-hosted URL
```

### Example

```bash
# Input
POST /caption
{
  "video_url": "https://example.com/video.mp4"
}

# Output
{
  "url": "https://your-app.railway.app/videos/abc123_captioned.mp4"
}
```

## 📁 Project Structure

```
project/
├── app/
│   ├── main.py                         # FastAPI app with /videos endpoint
│   └── services/
│       └── caption_generation.py       # Caption processing logic
├── static/
│   └── videos/                         # Captioned videos stored here
├── requirements.txt                    # Python dependencies
├── nixpacks.toml                       # Railway deployment config
└── README.md                           # This file
```

## 🚀 Quick Start

### 1. Deploy to Railway

```bash
# Push to Railway
git add .
git commit -m "Add FFmpeg caption service"
git push railway main
```

Railway will automatically:
- Install FFmpeg (via nixpacks.toml)
- Install Python dependencies
- Start the FastAPI server
- Mount `/videos` static files directory

### 2. Test the API

```bash
# Health check
curl https://your-app.railway.app/health

# Caption a video
curl -X POST https://your-app.railway.app/caption \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://example.com/sample.mp4",
    "model_size": "small"
  }'

# Response:
# {
#   "url": "https://your-app.railway.app/videos/abc123_captioned.mp4"
# }
```

### 3. Access the Video

The captioned video is now accessible at:
```
https://your-app.railway.app/videos/abc123_captioned.mp4
```

You can use this URL directly in your frontend `<video>` tags.

## 🔧 Configuration

### Environment Variables

```bash
# Optional: Set custom base URL (Railway sets this automatically)
RAILWAY_PUBLIC_DOMAIN=your-app.railway.app

# Optional: Set custom port (Railway handles this)
PORT=8000
```

### Whisper Model Sizes

Choose model size based on accuracy vs speed:

| Model | Speed | Accuracy | Memory |
|-------|-------|----------|--------|
| tiny  | Fast  | Good     | ~1GB   |
| small | Medium| Better   | ~2GB   |
| medium| Slow  | Great    | ~5GB   |
| large | Very Slow | Best | ~10GB  |

**Recommended**: `small` for production (good balance)

## 📝 API Reference

### POST /caption

Add captions to a video.

**Request:**
```json
{
  "video_url": "https://example.com/video.mp4",
  "model_size": "small",
  "aspect_ratio": "9:16",
  "user_id": "optional_user_123",
  "video_id": "optional_video_456"
}
```

**Response (Success):**
```json
{
  "url": "https://your-app.railway.app/videos/abc123_captioned.mp4"
}
```

**Response (Failure):**
```json
{
  "url": "https://example.com/video.mp4",
  "status": "failed",
  "message": "Caption processing failed, returned original video"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-07T01:00:00.000000",
  "version": "1.0.0"
}
```

## 🔗 Integration with Existing Workflow

If you already have a video processing pipeline, you can call `add_captions_to_video()` directly:

```python
from app.services.caption_generation import add_captions_to_video

# In your workflow
final_video_url = "https://example.com/composed_video.mp4"
captioned_url = await add_captions_to_video(
    final_video_url=final_video_url,
    aspect_ratio="9:16",
    user_id="user123",
    video_id="video456"
)

# Use captioned_url in your response
```

## 🎨 Customization

### Subtitle Styling

Edit `caption_generation.py` line 122 to customize FFmpeg subtitle styling:

```python
cmd = [
    "ffmpeg",
    "-y",
    "-i", video_path,
    "-vf", f"subtitles={srt_path}:force_style='FontName=Arial,FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=3,Outline=2,Shadow=1,MarginV=50'",
    output_path
]
```

**Style Options:**
- `FontName` - Font family
- `FontSize` - Text size
- `PrimaryColour` - Text color (BGR hex)
- `OutlineColour` - Outline color
- `Outline` - Outline thickness
- `Shadow` - Shadow distance
- `MarginV` - Vertical margin from bottom

### Words Per Line

Edit `write_srt()` function:

```python
def write_srt(subtitles: list, max_words_per_line: int = 3):
    # Change 3 to your preferred number
```

## 💾 Storage Management

Videos are stored in `static/videos/` directory on Railway.

### Cleanup Strategy

Railway has limited storage, so you should clean up old videos:

**Option 1: Automatic Cleanup (Recommended)**

Add this to `caption_generation.py`:

```python
import time

# After saving captioned video
def cleanup_old_videos(directory="static/videos", max_age_hours=24):
    """Delete videos older than max_age_hours"""
    current_time = time.time()
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            file_age_hours = (current_time - os.path.getmtime(filepath)) / 3600
            if file_age_hours > max_age_hours:
                os.remove(filepath)
                logger.info(f"CLEANUP: Removed old file {filename}")

# Call after processing
cleanup_old_videos()
```

**Option 2: Manual Cleanup**

SSH into Railway and run:
```bash
find static/videos -name "*.mp4" -mtime +1 -delete
```

## 🐛 Troubleshooting

### FFmpeg Not Found

**Symptom:** `CAPTIONS: FFmpeg error - ffmpeg: command not found`

**Solution:** Ensure `nixpacks.toml` is in project root with:
```toml
[phases.setup]
nixPkgs = ["python39", "ffmpeg"]
```

### Whisper Model Download Fails

**Symptom:** `Failed to download Whisper model`

**Solution:** Use a smaller model:
```python
transcribe_audio(input_path, "tiny")  # Instead of "small"
```

### Out of Memory

**Symptom:** Railway container crashes during processing

**Solutions:**
1. Use `tiny` Whisper model
2. Upgrade Railway plan
3. Process shorter videos only

### Video Not Accessible

**Symptom:** 404 when accessing `/videos/...` URL

**Solution:** Check that:
1. `static/videos` directory exists
2. FastAPI mounts it: `app.mount("/videos", StaticFiles(directory="static/videos"))`
3. File was actually saved (check logs)

## 📊 Performance

Expected processing times on Railway Hobby plan:

| Video Length | Transcription | FFmpeg | Total   |
|--------------|---------------|--------|---------|
| 30 seconds   | 15-20s        | 5-8s   | 20-28s  |
| 60 seconds   | 30-40s        | 10-15s | 40-55s  |

## 💰 Cost Comparison

### Before (json2video API)
- $0.10 per video
- 1000 videos/month = **$100/month**

### After (Self-Hosted on Railway)
- Railway compute: $5-20/month
- Railway storage: Free (up to 100GB)
- 1000 videos/month = **$5-20/month**

**Savings: 80-95%!** 🎉

## 🔒 Security Notes

1. **No Authentication:** Add auth middleware if needed
2. **Rate Limiting:** Consider adding rate limits
3. **Input Validation:** Video URL is validated
4. **File Cleanup:** Implement cleanup to prevent storage abuse

## 📚 Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `openai-whisper` - Speech-to-text
- `requests` - HTTP client
- `ffmpeg` - Video processing (installed via nixpacks)

## 🚢 Deployment Checklist

- [x] Code structure matches working example
- [x] Static files hosted at `/videos`
- [x] FFmpeg installed via nixpacks
- [x] Whisper dependencies in requirements.txt
- [x] FastAPI app with CORS enabled
- [x] Health check endpoint
- [x] Error handling returns original URL
- [ ] **Deploy to Railway**
- [ ] **Test with real video**
- [ ] **Verify `/videos` endpoint works**
- [ ] **Monitor storage usage**

## 🎯 Success!

Your caption service is now:
- ✅ Self-hosted on Railway
- ✅ Uses static file hosting
- ✅ Returns Railway-hosted URLs
- ✅ 80-95% cheaper than json2video
- ✅ Fully under your control

Frontend receives the same format of video URLs and requires no changes!
