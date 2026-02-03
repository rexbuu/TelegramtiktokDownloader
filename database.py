"""
Supabase Database Integration (REST API)
=========================================

Uses direct REST API calls to avoid supabase-py version issues.

Tables required in Supabase:
1. users - Track bot users
2. downloads - Track download history
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class Database:
    """
    Database wrapper using Supabase REST API.
    Falls back to in-memory storage if Supabase is not configured.
    """
    
    def __init__(self, supabase_url: str = "", supabase_key: str = ""):
        self.supabase_url = supabase_url.rstrip('/')
        self.supabase_key = supabase_key
        self.rest_url = f"{self.supabase_url}/rest/v1" if supabase_url else ""
        self.headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        } if supabase_key else {}
        
        self.connected = False
        
        # In-memory fallback
        self._memory_users = set()
        self._memory_downloads = []
    
    async def initialize(self):
        """Initialize and test the database connection"""
        if self.supabase_url and self.supabase_key:
            try:
                async with httpx.AsyncClient() as client:
                    # Test connection by checking users table
                    response = await client.get(
                        f"{self.rest_url}/users?select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    if response.status_code == 200:
                        self.connected = True
                        logger.info("Connected to Supabase (REST API)")
                    else:
                        logger.error(f"Supabase test failed: {response.status_code} - {response.text}")
                        self.connected = False
            except Exception as e:
                logger.error(f"Failed to connect to Supabase: {e}")
                self.connected = False
        
        if not self.connected:
            logger.info("Using in-memory storage")
    
    async def track_user(self, user_id: int, username: str):
        """Track a new user or update existing"""
        if self.connected:
            try:
                async with httpx.AsyncClient() as client:
                    # Upsert user
                    await client.post(
                        f"{self.rest_url}/users",
                        headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                        json={
                            'telegram_id': user_id,
                            'username': username,
                            'last_seen': datetime.now(timezone.utc).isoformat()
                        }
                    )
            except Exception as e:
                logger.error(f"Error tracking user: {e}")
        
        self._memory_users.add(user_id)
    
    async def track_download(self, user_id: int, url: str, success: bool):
        """Track a download attempt"""
        download_data = {
            'telegram_id': user_id,
            'url': url[:500],
            'success': success,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        if self.connected:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{self.rest_url}/downloads",
                        headers=self.headers,
                        json=download_data
                    )
            except Exception as e:
                logger.error(f"Error tracking download: {e}")
        
        self._memory_downloads.append({
            'user_id': user_id,
            'url': url,
            'success': success,
            'created_at': datetime.now(timezone.utc)
        })
    
    async def get_stats(self) -> dict:
        """Get aggregated statistics (for dashboard)"""
        if self.connected:
            try:
                async with httpx.AsyncClient() as client:
                    # Get total users
                    users_resp = await client.get(
                        f"{self.rest_url}/users?select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    total_users = int(users_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    # Get total downloads
                    downloads_resp = await client.get(
                        f"{self.rest_url}/downloads?select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    total_downloads = int(downloads_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    # Get successful downloads
                    success_resp = await client.get(
                        f"{self.rest_url}/downloads?success=eq.true&select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    successful_downloads = int(success_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    # Get today's downloads
                    today = datetime.now(timezone.utc).date().isoformat()
                    today_resp = await client.get(
                        f"{self.rest_url}/downloads?created_at=gte.{today}&select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    today_downloads = int(today_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    return {
                        'total_users': total_users,
                        'total_downloads': total_downloads,
                        'successful_downloads': successful_downloads,
                        'failed_downloads': total_downloads - successful_downloads,
                        'today_downloads': today_downloads
                    }
            except Exception as e:
                logger.error(f"Error getting stats from Supabase: {e}")
        
        # In-memory fallback
        today = datetime.now(timezone.utc).date()
        today_downloads = sum(
            1 for d in self._memory_downloads 
            if d['created_at'].date() == today
        )
        successful = sum(1 for d in self._memory_downloads if d['success'])
        
        return {
            'total_users': len(self._memory_users),
            'total_downloads': len(self._memory_downloads),
            'successful_downloads': successful,
            'failed_downloads': len(self._memory_downloads) - successful,
            'today_downloads': today_downloads
        }
    
    async def get_user_stats(self, user_id: int) -> dict:
        """Get statistics for a specific user only"""
        if self.connected:
            try:
                async with httpx.AsyncClient() as client:
                    # Get user's total downloads
                    total_resp = await client.get(
                        f"{self.rest_url}/downloads?telegram_id=eq.{user_id}&select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    total_downloads = int(total_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    # Get user's successful downloads
                    success_resp = await client.get(
                        f"{self.rest_url}/downloads?telegram_id=eq.{user_id}&success=eq.true&select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    successful_downloads = int(success_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    # Get user's today downloads
                    today = datetime.now(timezone.utc).date().isoformat()
                    today_resp = await client.get(
                        f"{self.rest_url}/downloads?telegram_id=eq.{user_id}&created_at=gte.{today}&select=count",
                        headers={**self.headers, "Prefer": "count=exact"}
                    )
                    today_downloads = int(today_resp.headers.get('content-range', '0-0/0').split('/')[-1])
                    
                    return {
                        'total_downloads': total_downloads,
                        'successful_downloads': successful_downloads,
                        'failed_downloads': total_downloads - successful_downloads,
                        'today_downloads': today_downloads
                    }
            except Exception as e:
                logger.error(f"Error getting user stats from Supabase: {e}")
        
        # In-memory fallback
        user_downloads = [d for d in self._memory_downloads if d['user_id'] == user_id]
        today = datetime.now(timezone.utc).date()
        today_downloads = sum(1 for d in user_downloads if d['created_at'].date() == today)
        successful = sum(1 for d in user_downloads if d['success'])
        
        return {
            'total_downloads': len(user_downloads),
            'successful_downloads': successful,
            'failed_downloads': len(user_downloads) - successful,
            'today_downloads': today_downloads
        }
