# Architecture Overview

## 📐 System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         RAILWAY SERVER                          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                      FastAPI App                          │ │
│  │                                                           │ │
│  │  ┌──────────────────┐       ┌──────────────────┐        │ │
│  │  │  GET /health     │       │  POST /caption   │        │ │
│  │  └──────────────────┘       └────────┬─────────┘        │ │
│  │                                       │                   │ │
│  │  ┌──────────────────┐                │                   │ │
│  │  │  GET /videos/*   │                │                   │ │
│  │  │  (Static Files)  │                │                   │ │
│  │  └────────┬─────────┘                │                   │ │
│  │           │                           ▼                   │ │
│  │           │            ┌──────────────────────────────┐  │ │
│  │           │            │  caption_generation.py      │  │ │
│  │           │            │                             │  │ │
│  │           │            │  • download_video()         │  │ │
│  │           │            │  • transcribe_audio()       │  │ │
│  │           │            │  • write_srt()              │  │ │
│  │           │            │  • burn_subtitles()         │  │ │
│  │           │            │  • add_captions_to_video()  │  │ │
│  │           │            └──────────┬───────────────────┘  │ │
│  │           │                       │                      │ │
│  └───────────┼───────────────────────┼──────────────────────┘ │
│              │                       │                        │
│  ┌───────────▼───────────────────────▼──────────────────────┐ │
│  │              static/videos/                              │ │
│  │                                                          │ │
│  │  abc123_input.mp4      (temp)                           │ │
│  │  abc123_captioned.mp4  (served via /videos endpoint)    │ │
│  │  def456_captioned.mp4                                   │ │
│  │  ...                                                     │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              System Dependencies                         │ │
│  │                                                          │ │
│  │  • Python 3.9                                           │ │
│  │  • FFmpeg (installed via nixpacks)                     │ │
│  │  • Whisper models (downloaded on first use)            │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 🔄 Request Flow

```
1. CLIENT REQUEST
   ↓
   POST /caption {"video_url": "https://source.com/video.mp4"}
   ↓

2. DOWNLOAD
   ↓
   Download video to: static/videos/abc123_input.mp4
   ↓

3. TRANSCRIBE
   ↓
   Whisper processes audio → segments array
   ↓

4. GENERATE SUBTITLES
   ↓
   Convert segments → SRT format → abc123_temp.srt
   ↓

5. BURN SUBTITLES
   ↓
   FFmpeg: input.mp4 + temp.srt → static/videos/abc123_captioned.mp4
   ↓

6. CLEANUP
   ↓
   Delete: abc123_input.mp4, abc123_temp.srt
   ↓

7. RESPONSE
   ↓
   {"url": "https://your-app.railway.app/videos/abc123_captioned.mp4"}
   ↓

8. CLIENT ACCESSES VIDEO
   ↓
   GET /videos/abc123_captioned.mp4
   ↓
   Static file served directly from Railway
```

## 📦 File Organization

```
project/
│
├── app/
│   ├── __init__.py
│   ├── main.py                          ← FastAPI app entry point
│   │   └── Mounts: /videos → static/videos/
│   │
│   └── services/
│       ├── __init__.py
│       └── caption_generation.py        ← Core processing logic
│
├── static/
│   └── videos/                          ← Processed videos stored here
│       ├── abc123_captioned.mp4
│       ├── def456_captioned.mp4
│       └── ...
│
├── requirements.txt                     ← Python dependencies
├── nixpacks.toml                        ← Railway build config
├── test_caption.py                      ← Test script
│
└── Documentation/
    ├── README.md                        ← Main documentation
    ├── DEPLOYMENT.md                    ← Deployment guide
    ├── ARCHITECTURE.md                  ← This file
    └── SUMMARY.md                       ← Quick overview
```

## 🧩 Component Interactions

```
┌──────────────┐
│   Frontend   │
└──────┬───────┘
       │ HTTP POST
       ▼
┌──────────────────────────────┐
│   FastAPI /caption endpoint  │
└──────────────┬───────────────┘
               │ async call
               ▼
┌──────────────────────────────────────┐
│   add_captions_to_video()           │
│                                      │
│   ┌─────────────────────────────┐  │
│   │  1. download_video()        │  │
│   │     ↓ requests.get()        │  │
│   │     ↓ save to disk          │  │
│   └─────────────────────────────┘  │
│                                      │
│   ┌─────────────────────────────┐  │
│   │  2. transcribe_audio()      │  │
│   │     ↓ whisper.load_model()  │  │
│   │     ↓ model.transcribe()    │  │
│   └─────────────────────────────┘  │
│                                      │
│   ┌─────────────────────────────┐  │
│   │  3. write_srt()             │  │
│   │     ↓ format segments       │  │
│   │     ↓ generate timecodes    │  │
│   └─────────────────────────────┘  │
│                                      │
│   ┌─────────────────────────────┐  │
│   │  4. burn_subtitles()        │  │
│   │     ↓ subprocess.run()      │  │
│   │     ↓ ffmpeg command        │  │
│   └─────────────────────────────┘  │
│                                      │
│   ┌─────────────────────────────┐  │
│   │  5. return Railway URL      │  │
│   └─────────────────────────────┘  │
└──────────────┬───────────────────────┘
               │ Railway-hosted URL
               ▼
┌──────────────────────────────┐
│   Frontend plays video       │
│   from Railway static files  │
└──────────────────────────────┘
```

## 🔐 Data Flow Security

```
1. Input Validation
   ✓ Video URL must start with http/https
   ✓ File extensions validated
   ✓ Timeouts on downloads

2. Processing Isolation
   ✓ Each request gets unique ID
   ✓ Temporary files separated
   ✓ Cleanup after processing

3. Output Safety
   ✓ Static file serving (read-only)
   ✓ No directory traversal
   ✓ CORS configured
```

## ⚙️ Configuration Flow

```
Railway Environment
    ↓
nixpacks.toml
    ↓ installs
FFmpeg + Python
    ↓
requirements.txt
    ↓ installs
Whisper + FastAPI + requests
    ↓
app/main.py
    ↓ starts
FastAPI Server (Port from $PORT)
    ↓
Static Files Mounted (/videos)
    ↓
Ready to Accept Requests
```

## 📊 Performance Characteristics

### Processing Pipeline
```
Download: ~5-15s   ████████░░░░░░░░░░░░ (20%)
Whisper:  ~15-40s  ████████████████████░ (60%)
FFmpeg:   ~5-15s   ████████░░░░░░░░░░░░ (20%)
─────────────────────────────────────────
Total:    ~25-70s  per 30-60 second video
```

### Storage Growth
```
Per video: ~10-50MB
Daily (100 videos): ~1-5GB
Monthly: ~30-150GB

⚠️ Remember to implement cleanup!
```

## 🔄 Comparison with json2video

```
┌─────────────────────────────────────────────────────┐
│                    json2video                       │
├─────────────────────────────────────────────────────┤
│  Client → json2video API → Poll status             │
│         → Receive CDN URL → Play video              │
│                                                     │
│  Pros: Simple, no infrastructure                   │
│  Cons: $$$, slow, no control                       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              This (Railway + FFmpeg)                │
├─────────────────────────────────────────────────────┤
│  Client → Your API → Process locally                │
│         → Receive Railway URL → Play video          │
│                                                     │
│  Pros: Cheap, fast, full control                   │
│  Cons: Need to manage infrastructure               │
└─────────────────────────────────────────────────────┘
```

## 🎯 Key Design Decisions

### 1. Async Processing
```python
# Why async?
- Doesn't block other requests
- Better resource utilization
- Can handle multiple videos simultaneously
```

### 2. Static File Hosting
```python
# Why not Supabase Storage?
- Simpler (no SDK needed)
- Faster (direct serving)
- Cheaper (no storage API fees)
- Easier to debug
```

### 3. Fallback to Original URL
```python
# Why return original on failure?
- Never breaks frontend
- Graceful degradation
- Easy to monitor failures
```

### 4. Unique IDs per Request
```python
# Why UUIDs?
- Prevents file collisions
- Easy to track processing
- Safe for concurrent requests
```

## 🚀 Scalability Considerations

### Current Setup (Railway Hobby)
```
Concurrent Requests: ~2-3
Processing Time: 25-70s/video
Storage: Up to 100GB
Cost: $5-20/month
```

### Scaling Options
```
1. Vertical Scaling (Upgrade Plan)
   - More CPU → Faster Whisper
   - More RAM → Larger models
   - More storage → More videos

2. Horizontal Scaling (Multiple Instances)
   - Load balancer
   - Shared storage (S3, etc.)
   - Queue system (Redis)

3. Optimization
   - Smaller Whisper models
   - Video compression
   - Aggressive cleanup
```

## 🎉 Summary

This architecture provides:
- ✅ Simple, maintainable structure
- ✅ Cost-effective processing
- ✅ Railway-hosted video URLs
- ✅ Matches your working example
- ✅ Production-ready error handling
- ✅ Easy to scale and modify

**Ready to deploy!** 🚀
