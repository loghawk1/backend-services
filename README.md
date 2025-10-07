# Video Generation Service with JSON2Video Captions

AI-powered video generation service with automated caption generation using JSON2Video API.

## 🎯 How It Works

### Simple Architecture

```
Video Request
  ↓
Generate scenes with GPT-4
  ↓
Create images & videos with fal.ai
  ↓
Generate voiceovers & music
  ↓
Compose final video with JSON2Video
  ↓
Add auto-generated captions with JSON2Video
  ↓
Return final video URL
```

### Example

```bash
# Input
POST /video/request
{
  "prompt": "A story about...",
  "image_url": "https://example.com/image.jpg",
  "aspect_ratio": "9:16"
}

# Output
{
  "video_id": "abc123",
  "status": "processing"
}
```

## 📁 Project Structure

```
project/
├── app/
│   ├── main.py                         # FastAPI app
│   ├── worker.py                       # ARQ task worker
│   └── services/
│       ├── scene_generation.py         # GPT-4 scene generation
│       ├── image_processing.py         # Image generation
│       ├── video_generation.py         # Video generation
│       ├── audio_generation.py         # Voiceover generation
│       ├── music_generation.py         # Music generation
│       ├── json2video_composition.py   # Video composition
│       └── caption_generation.py       # Caption generation with JSON2Video
├── requirements.txt                    # Python dependencies
└── README.md                           # This file
```

## 🚀 Quick Start

### Environment Variables

Required environment variables:

```bash
# APIs
OPENAI_API_KEY=your_openai_key
FAL_KEY=your_fal_key
JSON2VIDEO_API_KEY=your_json2video_key

# Database
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Redis (for task queue)
REDIS_URL=redis://localhost:6379
```

### Running Locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start Redis:
```bash
redis-server
```

3. Run the worker:
```bash
python run_worker.py
```

4. Run the server:
```bash
python run_server.py
```

## 📝 API Reference

### POST /video/request

Generate a video from a prompt.

**Request:**
```json
{
  "prompt": "A story about innovation",
  "image_url": "https://example.com/image.jpg",
  "aspect_ratio": "9:16",
  "user_email": "user@example.com",
  "callback_url": "https://your-app.com/webhook"
}
```

**Response:**
```json
{
  "video_id": "abc123",
  "status": "processing",
  "task_id": "task_xyz"
}
```

### POST /video/wan-request

Generate a video using the WAN workflow (6 scenes).

**Request:**
```json
{
  "prompt": "Product advertisement",
  "image_url": "https://example.com/product.jpg",
  "aspect_ratio": "9:16",
  "model": "wan"
}
```

### POST /video/revision

Revise an existing video.

**Request:**
```json
{
  "parent_video_id": "video_123",
  "revision_request": "Make it more energetic",
  "user_email": "user@example.com"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-07T01:00:00.000000"
}
```

## 🎨 Caption Customization

### JSON2Video Caption Settings

Captions are automatically generated and burned into the video using JSON2Video's subtitle feature. The service:

1. Transcribes audio from the video
2. Generates word-by-word captions
3. Burns them into the video with custom styling

Current caption style:
- Font: Nunito
- Size: 70px
- Color: White with black outline
- Position: Bottom center
- Max words per line: 3

To customize captions, edit `app/services/caption_generation.py`:

```python
"subtitles": {
    "settings": {
        "style": "classic",
        "font-family": "Nunito",
        "font-size": 70,
        "word-color": "#FFFFFF",
        "outline-color": "#000000",
        "max-words-per-line": 3,
        "position": "custom",
        "y": 1400
    }
}
```

## 🔧 How Caption Generation Works

The caption workflow uses JSON2Video API:

1. **Input**: Final composed video URL
2. **Process**: JSON2Video API call with subtitle element
3. **Transcription**: Automatic speech-to-text
4. **Rendering**: Captions burned into video
5. **Output**: New video URL with captions

```python
from app.services.caption_generation import add_captions_to_video

# In your workflow
final_video_url = "https://example.com/composed_video.mp4"
captioned_url = await add_captions_to_video(
    final_video_url=final_video_url,
    aspect_ratio="9:16"
)
```

If caption generation fails, the original video URL is returned as fallback.

## 🐛 Troubleshooting

### Caption Generation Fails

**Symptom:** Original video returned without captions

**Possible causes:**
1. JSON2VIDEO_API_KEY not set
2. Invalid video URL
3. API quota exceeded
4. Network timeout

**Solution:** Check logs for detailed error messages:
```bash
tail -f app.log
```

### Video Processing Timeout

**Symptom:** Task times out after 10 minutes

**Solution:**
- Check ARQ worker logs
- Verify all API keys are set
- Ensure Redis is running

## 📊 Performance

Expected processing times:

| Step | Time |
|------|------|
| Scene generation (GPT-4) | 10-15s |
| Image generation (fal.ai) | 30-60s |
| Video generation (fal.ai) | 60-120s |
| Voiceover generation | 20-30s |
| Music generation | 15-20s |
| Video composition | 30-60s |
| Caption generation | 60-120s |
| **Total** | **4-7 minutes** |

## 🔒 Security Notes

1. **API Key Protection:** Never commit API keys to git
2. **Webhook Security:** Validate callback URLs
3. **Rate Limiting:** Implement rate limits on endpoints
4. **Input Validation:** All inputs are validated

## 📚 Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `arq` - Task queue
- `redis` - Task queue backend
- `openai` - GPT-4 for scene generation
- `fal-client` - Image/video/audio generation
- `httpx` - HTTP client for API calls
- `supabase` - Database client

## 🚢 Deployment

The service can be deployed to any platform that supports:
- Python 3.9+
- Redis
- Long-running workers (for ARQ)

Recommended platforms:
- Railway (with Redis addon)
- Heroku (with Redis addon)
- AWS ECS + ElastiCache
- Google Cloud Run + Memorystore

## 🎯 Success!

Your video generation service:
- ✅ Generates videos from text prompts
- ✅ Creates custom scenes with GPT-4
- ✅ Auto-generates voiceovers and music
- ✅ Adds professional captions automatically
- ✅ Supports video revisions
- ✅ Scales with async task queue
