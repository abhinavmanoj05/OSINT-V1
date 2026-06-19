"""
API dependencies
"""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.core.database import get_db, get_neo4j, async_session_maker
from backend.core.security import decode_token, get_current_user
from backend.core.config import settings


# Re-export database dependencies
get_db = get_db
get_neo4j = get_neo4j


async def get_current_active_user(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """Get current authenticated user"""
    return await get_current_user(credentials)


async def verify_case_access(case_id: str, user: dict = Depends(get_current_active_user)):
    """Verify user has access to specific case"""
    # In production, check if user is assigned to case
    # For now, allow all authenticated users
    return user


def get_redis_client():
    """Get Redis client for caching"""
    import redis
    return redis.from_url(settings.REDIS_URL)