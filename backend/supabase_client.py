"""Supabase client initialization for backend."""

from supabase import create_client
from config import get_config, validate_config

# Validate configuration on import
validate_config()

config = get_config()

# Initialize Supabase client with service role key (for backend operations)
# This allows bypassing RLS policies for server-side processing
supabase = create_client(
    supabase_url=config.SUPABASE_URL,
    supabase_key=config.SUPABASE_SERVICE_ROLE_KEY,
)


def get_supabase():
    """Get the Supabase client instance."""
    return supabase
