"""
Supabase client configuration using direct postgrest client to avoid proxy issues
"""
import httpx
from postgrest import SyncPostgrestClient
from .config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

class SupabaseClient:
    """Simple Supabase client wrapper using postgrest directly"""
    
    def __init__(self, url: str, service_role_key: str):
        self.url = url.strip()
        self.service_role_key = service_role_key.strip()
        self.rest_url = f"{url}/rest/v1"
        
        # Create postgrest client
        self.postgrest = SyncPostgrestClient(
            self.rest_url,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            }
        )
    
    def table(self, table_name: str):
        """Get table interface"""
        return self.postgrest.table(table_name)

def get_supabase_client() -> SupabaseClient:
    """Get Supabase client with service role key for backend operations"""
    logger.info("SUPABASE: Creating direct postgrest client...")
    
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("SUPABASE: Missing Supabase configuration")
        raise ValueError("Supabase URL and Service Role Key must be configured")
    
    try:
        logger.info(f"SUPABASE: Connecting to: {settings.supabase_url}")
        
        # Create direct postgrest client to avoid proxy issues
        client = SupabaseClient(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
        logger.info("SUPABASE: Direct postgrest client created successfully")
        return client
        
    except Exception as e:
        logger.error(f"SUPABASE: Failed to create client: {e}")
        logger.exception("Full traceback:")
        raise
