import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Redis Configuration (explicitly required for Railway)
    redis_url: str

    # API Configuration
    api_title: str = "Video Processing Webhook API"
    api_version: str = "1.0.0"
    debug: bool = False

    # Task Configuration
    max_concurrent_tasks: int = 10  # Reduced per replica, but with 3 replicas = 30 total
    task_timeout: int = 1200  # Increase to 20 minutes to allow proper error handling

    # External API Keys
    fal_key: str = ""
    openai_api_key: str = ""
    json2video_api_key: str = ""  # Deprecated - kept for backward compatibility
    dashscope_api_key: str = ""

    # FFmpeg Video Processing API Configuration
    ffmpeg_api_base_url: str = "https://fantastic-endurance-production.up.railway.app"
    ffmpeg_api_key: str = ""  # Optional - for future authentication

    # Supabase Configuration
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Callback Authentication
    callback_auth_token: str = ""
    webhook_secret: str = ""

    # Base44 App Configuration
    base44_app_id: str = ""

# Singleton instance of settings
_settings: Settings = None

def get_settings() -> Settings:
    """Get application settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
