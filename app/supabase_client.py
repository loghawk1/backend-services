"""
Supabase client configuration
"""
from supabase import create_client, Client
from .config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

def get_supabase_client() -> Client:
    """Get Supabase client with service role key for backend operations"""
    logger.info("SUPABASE: Creating Supabase client...")
    
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("SUPABASE: Missing Supabase configuration")
        raise ValueError("Supabase URL and Service Role Key must be configured")
    
    try:
        # Use the most basic client creation to avoid compatibility issues
        logger.info(f"SUPABASE: Connecting to: {settings.supabase_url}")
        
        # Create basic client without complex options
        client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
        logger.info("SUPABASE: Client created successfully")
        return client
    except Exception as e:
        logger.error(f"SUPABASE: Failed to create client: {e}")
        logger.exception("Full traceback:")
        raise

    
    return client
