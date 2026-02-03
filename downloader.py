"""
SSSTIK Downloader - HTTP Version
================================

Lightweight HTTP-based downloader for the bot service.
No browser required - uses direct API calls.
"""

import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SsstikDownloader:
    """
    HTTP-based TikTok downloader using ssstik.io API.
    """
    
    BASE_URL = "https://ssstik.io"
    PAGE_URL = "https://ssstik.io/en-1"
    API_URL = "https://ssstik.io/abc?url=dl"
    DOWNLOAD_DIR = Path("/tmp/downloads")
    
    def __init__(self):
        self.DOWNLOAD_DIR.mkdir(exist_ok=True)
    
    async def _get_token(self, client: httpx.AsyncClient) -> str:
        """Fetch the 'tt' token from ssstik.io page."""
        logger.info("Fetching page token...")
        
        response = await client.get(self.PAGE_URL)
        
        if response.status_code != 200:
            raise Exception(f"Failed to load page: {response.status_code}")
        
        html = response.text
        
        # Try to find the 'tt' token
        patterns = [
            r"name=['\"]tt['\"].*?value=['\"]([^'\"]+)['\"]",
            r"tt\s*[:=]\s*['\"]([^'\"]+)['\"]",
            r"data-tt=['\"]([^'\"]+)['\"]"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Try BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        tt_input = soup.find('input', {'name': 'tt'})
        if tt_input and tt_input.get('value'):
            return tt_input['value']
        
        # Look in script tags
        for script in soup.find_all('script'):
            if script.string and 'tt' in str(script.string):
                match = re.search(r"tt\s*[:=]\s*['\"]([^'\"]+)['\"]", str(script.string))
                if match:
                    return match.group(1)
        
        raise Exception("Could not find 'tt' token")
    
    async def _fetch_download_links(
        self, 
        client: httpx.AsyncClient, 
        tiktok_url: str, 
        token: str
    ) -> str:
        """Call the ssstik.io API to get download link."""
        logger.info("Calling ssstik.io API...")
        
        data = {
            'id': tiktok_url,
            'locale': 'en',
            'tt': token
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'HX-Request': 'true',
            'HX-Trigger': '_gcaptcha_pt',
            'HX-Target': 'target',
            'HX-Current-URL': self.PAGE_URL,
            'Origin': self.BASE_URL,
            'Referer': self.PAGE_URL
        }
        
        response = await client.post(self.API_URL, data=data, headers=headers)
        
        if response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code}")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find download links
        download_url = None
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text().lower()
            
            if 'tikcdn.io' in href or '.mp4' in href:
                if 'without' in text or 'no watermark' in text:
                    download_url = href
                    break
                elif not download_url:
                    download_url = href
        
        if not download_url:
            raise Exception("No download link found")
        
        # Ensure URL is absolute
        if download_url.startswith('//'):
            download_url = 'https:' + download_url
        elif download_url.startswith('/'):
            download_url = self.BASE_URL + download_url
        
        return download_url
    
    async def download_video(self, tiktok_url: str) -> dict:
        """Download a TikTok video."""
        result = {
            'success': False,
            'url': tiktok_url,
            'download_path': None,
            'error': None,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=60.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        ) as client:
            try:
                # Get token
                token = await self._get_token(client)
                
                # Get download link
                download_url = await self._fetch_download_links(client, tiktok_url, token)
                logger.info(f"Download URL: {download_url[:80]}...")
                
                # Download video
                video_response = await client.get(
                    download_url,
                    headers={'Referer': 'https://ssstik.io/'}
                )
                
                if video_response.status_code != 200:
                    raise Exception(f"Download failed: {video_response.status_code}")
                
                # Save file
                video_id = self._extract_video_id(tiktok_url)
                filename = f"ssstik_{video_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.mp4"
                download_path = self.DOWNLOAD_DIR / filename
                
                with open(download_path, 'wb') as f:
                    f.write(video_response.content)
                
                logger.info(f"Downloaded: {filename}")
                
                result['success'] = True
                result['download_path'] = str(download_path)
                
            except Exception as e:
                logger.error(f"Error: {e}")
                result['error'] = str(e)
        
        return result
    
    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from TikTok URL."""
        patterns = [
            r'/video/(\d+)',
            r'/v/(\d+)',
            r'(\d{19})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return datetime.utcnow().strftime('%Y%m%d%H%M%S')
