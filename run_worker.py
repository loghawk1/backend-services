#!/usr/bin/env python3
"""
Run the ARQ worker for processing tasks
"""
import asyncio
from arq import run_worker
from app.worker import WorkerSettings
from app.config import get_settings

# Get settings to ensure timeout is loaded
settings = get_settings()
print(f"Worker starting with ARQ job timeout: {WorkerSettings.job_timeout} seconds")
print(f"Worker max concurrent jobs: {WorkerSettings.max_jobs}")
print(f"Worker max tries per job: {WorkerSettings.max_tries}")

if __name__ == "__main__":
    run_worker(WorkerSettings)