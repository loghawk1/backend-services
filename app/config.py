from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str = "redis://localhost:6379/0"

    # API Configuration
    api_title: str = "Video Processing Webhook API"
    api_version: str = "1.0.0"
    debug: bool = False

    # Task Configuration
    max_concurrent_tasks: int = 100
    task_timeout: int = 900  # Increase to 15 minutes for music generation

    # External API Keys
    fal_key: str
    openai_api_key: str
    json2video_api_key: str

    # Supabase Configuration
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

# Singleton instance of settings
_settings: Settings = None

def get_settings() -> Settings:
    """Get application settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings