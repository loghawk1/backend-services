#!/usr/bin/env python3
"""
Run the FastAPI server with optimal settings for high concurrency
"""
import os
import uvicorn

if __name__ == "__main__":
    # Use PORT environment variable from Railway, fallback to 8000 for local development
    port = int(os.getenv("PORT", "8000"))
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,   # Disable for production
        workers=1,      # Single worker for Windows compatibility
        log_level="info"
    )
