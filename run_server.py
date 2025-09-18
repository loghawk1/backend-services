#!/usr/bin/env python3
"""
Run the FastAPI server with optimal settings for high concurrency
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,   # Disable for production
        workers=1,      # Single worker for Windows compatibility
        log_level="info"
    )