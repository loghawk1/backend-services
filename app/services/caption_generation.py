import os
import uuid
import asyncio
import logging
import requests
import whisper
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def download_video(video_url: str, output_path: str) -> bool:
    """Download video from a URL."""
    try:
        logger.info(f"CAPTIONS: Downloading video from {video_url}")
        response = requests.get(video_url, stream=True, timeout=300)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"CAPTIONS: Download complete - {output_path}")
        return True
    except Exception as e:
        logger.error(f"CAPTIONS: Download failed - {e}")
        return False


def transcribe_audio(video_path: str, model_size: str = "small") -> Optional[list]:
    """Transcribe audio from video using Whisper."""
    try:
        logger.info(f"CAPTIONS: Loading Whisper model ({model_size})...")
        model = whisper.load_model(model_size)

        logger.info("CAPTIONS: Transcribing audio...")
        result = model.transcribe(video_path)

        segments = result.get("segments", [])
        logger.info(f"CAPTIONS: Transcription complete - {len(segments)} segments")
        return segments
    except Exception as e:
        logger.error(f"CAPTIONS: Transcription failed - {e}")
        return None


def write_srt(subtitles: list, max_words_per_line: int = 3) -> str:
    """Convert Whisper segments into .srt subtitle format."""
    try:
        srt_output = []
        counter = 1

        for seg in subtitles:
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "").strip()

            if not text:
                continue

            words = text.split()
            duration = end - start

            chunks = [text] if len(words) <= max_words_per_line else [
                " ".join(words[i:i + max_words_per_line])
                for i in range(0, len(words), max_words_per_line)
            ]

            chunk_duration = duration / len(chunks) if chunks else duration

            def fmt_time(t):
                h, rem = divmod(t, 3600)
                m, s = divmod(rem, 60)
                ms = int((s - int(s)) * 1000)
                return f"{int(h):02}:{int(m):02}:{int(s):02},{ms:03}"

            for idx, chunk in enumerate(chunks):
                chunk_start = start + (idx * chunk_duration)
                chunk_end = start + ((idx + 1) * chunk_duration)
                srt_output.append(
                    f"{counter}\n{fmt_time(chunk_start)} --> {fmt_time(chunk_end)}\n{chunk}\n"
                )
                counter += 1

        result = "\n".join(srt_output)
        logger.info(f"CAPTIONS: Generated {counter - 1} subtitle entries")
        return result
    except Exception as e:
        logger.error(f"CAPTIONS: SRT generation failed - {e}")
        return ""


def burn_subtitles(video_path: str, srt_text: str, output_path: str) -> bool:
    """Add subtitles to video using ffmpeg."""
    try:
        srt_path = video_path.replace(".mp4", "_temp.srt")

        logger.info(f"CAPTIONS: Writing SRT file - {srt_path}")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_text)

        logger.info("CAPTIONS: Running FFmpeg to burn subtitles...")

        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vf", f"subtitles={srt_path}",
            output_path
        ]

        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if process.returncode != 0:
            logger.error(f"CAPTIONS: FFmpeg error - {process.stderr}")
            return False

        logger.info(f"CAPTIONS: Subtitles burned successfully - {output_path}")

        os.remove(srt_path)
        logger.info("CAPTIONS: Temporary SRT file cleaned up")

        return True
    except Exception as e:
        logger.error(f"CAPTIONS: Failed to burn subtitles - {e}")
        return False


async def add_captions_to_video(
    final_video_url: str,
    aspect_ratio: str = "9:16",
    user_id: str = "",
    video_id: str = ""
) -> str:
    """
    Add captions to video using FFmpeg and host on Railway static files.

    Args:
        final_video_url: The final composed video URL
        aspect_ratio: Video aspect ratio (e.g., "9:16", "16:9", "1:1", "3:4", "4:3")
        user_id: User ID (for logging)
        video_id: Video ID (for file naming)

    Returns:
        Captioned video URL hosted on Railway if successful, original URL if failed
    """
    try:
        logger.info("CAPTIONS: Starting caption workflow...")
        logger.info(f"CAPTIONS: Input video: {final_video_url}")
        logger.info(f"CAPTIONS: Video ID: {video_id}")

        if not final_video_url or not final_video_url.startswith("http"):
            logger.error(f"CAPTIONS: Invalid input video URL: {final_video_url}")
            return final_video_url

        os.makedirs("static/videos", exist_ok=True)

        uid = str(uuid.uuid4())[:8]
        input_path = f"static/videos/{uid}_input.mp4"
        output_path = f"static/videos/{uid}_captioned.mp4"

        loop = asyncio.get_event_loop()

        success = await loop.run_in_executor(None, download_video, final_video_url, input_path)
        if not success:
            logger.error("CAPTIONS: Download failed, returning original video")
            return final_video_url

        subtitles = await loop.run_in_executor(None, transcribe_audio, input_path, "small")
        if not subtitles:
            logger.error("CAPTIONS: Transcription failed, returning original video")
            if os.path.exists(input_path):
                os.remove(input_path)
            return final_video_url

        srt_text = await loop.run_in_executor(None, write_srt, subtitles, 3)
        if not srt_text:
            logger.error("CAPTIONS: SRT generation failed, returning original video")
            if os.path.exists(input_path):
                os.remove(input_path)
            return final_video_url

        success = await loop.run_in_executor(None, burn_subtitles, input_path, srt_text, output_path)
        if not success:
            logger.error("CAPTIONS: Subtitle burning failed, returning original video")
            if os.path.exists(input_path):
                os.remove(input_path)
            return final_video_url

        base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", "https://backend-services-production-c796.up.railway.app")
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        video_url_public = f"{base_url}/videos/{uid}_captioned.mp4"

        logger.info("CAPTIONS: Caption workflow completed successfully!")
        logger.info(f"CAPTIONS: Captioned video URL: {video_url_public}")

        if os.path.exists(input_path):
            os.remove(input_path)
            logger.info("CAPTIONS: Cleaned up input file")

        return video_url_public

    except Exception as e:
        logger.error(f"CAPTIONS: Caption workflow failed: {e}")
        logger.exception("Full traceback:")
        return final_video_url
