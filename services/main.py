from fastapi import FastAPI, Request
from arq.connections import ArqRedis

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()

    # Extract fields you need
    payload = {
        "prompt": body.get("prompt"),
        "image_url": body.get("image_url"),
        "video_id": body.get("video_id"),
        "chat_id": body.get("chat_id"),
        "user_id": body.get("user_id"),
        "user_email": body.get("user_email"),
        "user_name": body.get("user_name"),
        "is_revision": body.get("is_revision"),
        "request_timestamp": body.get("request_timestamp"),
        "source": body.get("source"),
        "version": body.get("version"),
        "idempotency_key": body.get("idempotency_key"),
        "callback_url": body.get("callback_url"),
        "webhookUrl": body.get("webhookUrl"),
        "executionMode": body.get("executionMode"),
    }

    # Log for debugging
    print("🎯 Received payload:", payload)

    # Push to ARQ worker
    redis = await ArqRedis.create(host="localhost", port=6379)
    await redis.enqueue_job("run_pipeline", payload)

    return {"status": "received", "data": payload}
