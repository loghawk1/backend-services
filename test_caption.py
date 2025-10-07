#!/usr/bin/env python3
"""
Simple test script for caption service
"""
import asyncio
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_imports():
    """Test that all dependencies can be imported"""
    logger.info("=" * 60)
    logger.info("TESTING IMPORTS")
    logger.info("=" * 60)

    try:
        import fastapi
        logger.info("✅ FastAPI imported")
    except ImportError as e:
        logger.error(f"❌ FastAPI import failed: {e}")
        return False

    try:
        import requests
        logger.info("✅ Requests imported")
    except ImportError as e:
        logger.error(f"❌ Requests import failed: {e}")
        return False

    try:
        import whisper
        logger.info("✅ Whisper imported")
    except ImportError as e:
        logger.error(f"❌ Whisper import failed: {e}")
        return False

    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            logger.info(f"✅ FFmpeg available: {version}")
        else:
            logger.error("❌ FFmpeg not working")
            return False
    except FileNotFoundError:
        logger.error("❌ FFmpeg not found in PATH")
        logger.error("   Make sure nixpacks.toml is configured correctly")
        return False

    logger.info("\n✅ All dependencies available!")
    return True


async def test_caption_service():
    """Test the caption service with a dummy video"""
    logger.info("\n" + "=" * 60)
    logger.info("TESTING CAPTION SERVICE")
    logger.info("=" * 60)

    try:
        from app.services.caption_generation import add_captions_to_video

        test_video_url = "https://example.com/test.mp4"
        logger.info(f"Testing with URL: {test_video_url}")
        logger.info("(This will fail since it's a dummy URL, but tests the flow)")

        result = await add_captions_to_video(
            final_video_url=test_video_url,
            aspect_ratio="9:16",
            user_id="test_user",
            video_id="test_video"
        )

        if result == test_video_url:
            logger.info("✅ Function executed and returned fallback URL (expected)")
            return True
        else:
            logger.error(f"❌ Unexpected result: {result}")
            return False

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api():
    """Test the FastAPI app structure"""
    logger.info("\n" + "=" * 60)
    logger.info("TESTING API STRUCTURE")
    logger.info("=" * 60)

    try:
        from app.main import app
        logger.info("✅ FastAPI app imported successfully")

        routes = [route.path for route in app.routes]
        logger.info(f"✅ Available routes: {routes}")

        if "/" in routes:
            logger.info("✅ Health check route exists")
        if "/caption" in routes:
            logger.info("✅ Caption endpoint exists")
        if "/videos" in routes:
            logger.info("✅ Static files endpoint exists")

        return True

    except Exception as e:
        logger.error(f"❌ API structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test runner"""
    logger.info("\n" + "=" * 60)
    logger.info("CAPTION SERVICE TEST SUITE")
    logger.info("=" * 60 + "\n")

    results = []

    results.append(await test_imports())
    results.append(await test_api())

    if "--full" in sys.argv:
        logger.info("\nRunning full caption service test...")
        results.append(await test_caption_service())

    logger.info("\n" + "=" * 60)
    logger.info("TEST RESULTS")
    logger.info("=" * 60)

    passed = sum(results)
    total = len(results)

    logger.info(f"Passed: {passed}/{total}")

    if passed == total:
        logger.info("✅ All tests passed!")
        return 0
    else:
        logger.error("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
