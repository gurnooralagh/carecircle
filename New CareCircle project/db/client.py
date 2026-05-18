import functools
from supabase import create_client, Client
from config.settings import settings


@functools.lru_cache()
def get_supabase() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


def get_db() -> Client:
    return get_supabase()
