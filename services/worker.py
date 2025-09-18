import asyncio
import logging
from arq.connections import RedisSettings

logging.basicConfig(level=logging.INFO)

async def run_pipeline(ctx, payload: dict):
    logging.info("⚡ Processing pipeline task")
    logging.info(f"Prompt: {payload.get('prompt')[:100]}...")  # just show first 100 chars
    logging.info(f"Image URL: {payload.get('image_url')}")

    # Simulate heavy processing (e.g., video generation, uploading)
    await asyncio.sleep(5)

    logging.info(f"✅ Finished processing for: {payload.get('image_url')}")

class WorkerSettings:
    functions = [run_pipeline]
    redis_settings = RedisSettings()
