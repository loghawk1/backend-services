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
    task_timeout: int = 900  # Increase to 15 minutes for music generation

    # External API Keys
    fal_key: str = ""
    openai_api_key: str = ""
    json2video_api_key: str = ""

    # Supabase Configuration
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Callback Authentication
    callback_auth_token: str = ""
    webhook_secret: str = ""

# Singleton instance of settings
_settings: Settings = None

def get_settings() -> Settings:
    """Get application settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
