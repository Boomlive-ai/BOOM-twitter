import os
import aiohttp
import aiofiles
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import uuid
from urllib.parse import urlparse
import tempfile

logger = logging.getLogger(__name__)

class MediaProcessor:
    """Enhanced utility class to process Twitter media files via URL-based API"""
    
    def __init__(self, temp_dir: str = None):
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "twitter_media"
        self.temp_dir.mkdir(exist_ok=True)
        self.session = None
        self.processed_files = []  # Track files for cleanup (kept for compatibility)
        
    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session or self.session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
                headers={
                    'User-Agent': 'TwitterBot/1.0',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate'
                }
            )
        return self.session
    
    async def process_media_from_tweet(self, media_objects: List[Any], tweet_id: str, api_url: str) -> str:
        """
        Process media from tweet media objects using URL-based API
        
        Args:
            media_objects: List of media objects from tweepy response
            tweet_id: Tweet ID for tracking
            api_url: API URL for processing media
            
        Returns:
            Combined description string from all media
        """
        if not media_objects or not api_url:
            return ""
            
        all_descriptions = []
        
        for media in media_objects:
            try:
                # Get the appropriate URL based on media type
                media_url = await self._get_media_url(media)
                
                if not media_url:
                    logger.warning(f"⚠️ No URL found for media {media.media_key}")
                    continue
                
                logger.info(f"🖼️ Processing {media.type} via API: {media.media_key}")
                
                # Process media via URL-based API
                description = await self._process_media_url(media_url, api_url)
                
                if description:
                    all_descriptions.append(description)
                    logger.info(f"✅ Processed {media.type}: {len(description)} chars")
                else:
                    logger.warning(f"⚠️ No description returned for {media.media_key}")
                    
            except Exception as e:
                logger.error(f"❌ Error processing media {getattr(media, 'media_key', 'unknown')}: {e}")
                continue
        
        # Combine all descriptions
        combined_description = " | ".join(all_descriptions) if all_descriptions else ""
        logger.info(f"📝 Total media descriptions: {len(combined_description)} chars from {len(all_descriptions)} files")
        return combined_description
    
    async def _get_media_url(self, media) -> Optional[str]:
        """Extract download URL from media object based on type"""
        try:
            if media.type == 'photo':
                return media.url
            elif media.type in ['video', 'animated_gif']:
                # For videos and GIFs, get the best quality variant
                if hasattr(media, 'variants') and media.variants:
                    # Filter for mp4 videos first
                    mp4_variants = [v for v in media.variants 
                                  if v.get('content_type') == 'video/mp4']
                    
                    if mp4_variants:
                        # Get highest bitrate mp4
                        best_variant = max(mp4_variants, 
                                         key=lambda x: x.get('bit_rate', 0))
                        return best_variant['url']
                    else:
                        # Fallback to first available variant
                        return media.variants[0]['url']
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting media URL: {e}")
            return None
    
    async def _process_media_url(self, media_url: str, api_url: str) -> str:
        """Process media URL through the API and return description"""
        try:
            session = await self._get_session()
            
            # Prepare API request with URL parameter
            params = {
                'url': media_url
            }
            
            logger.info(f"🚀 Sending URL to media API: {media_url}")
            
            async with session.get(api_url, params=params) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    # Parse the new API response format
                    if result.get('success') and result.get('data'):
                        data = result['data']
                        
                        # Extract text from media results
                        if 'media_results' in data and data['media_results']:
                            descriptions = []
                            for media_result in data['media_results']:
                                # Try to get text description
                                text_desc = (media_result.get('text') or 
                                           media_result.get('summary') or 
                                           media_result.get('description') or '')
                                print(text_desc,"TEXT DESC")
                                if text_desc:
                                    descriptions.append(text_desc.strip())
                            
                            combined_desc = " | ".join(descriptions) if descriptions else ""
                            
                            if combined_desc:
                                logger.info(f"✅ Received description ({len(combined_desc)} chars)")
                                return combined_desc
                            else:
                                logger.warning(f"⚠️ No text content in API response")
                        else:
                            logger.warning(f"⚠️ No media_results in API response")
                    else:
                        error_msg = result.get('error', 'Unknown API error')
                        logger.error(f"❌ API returned error: {error_msg}")
                else:
                    response_text = await response.text()
                    logger.error(f"❌ Media API returned status {response.status}: {response_text}")
                    
        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout processing media URL: {media_url}")
        except Exception as e:
            logger.error(f"❌ Error processing media URL {media_url}: {e}")
                
        return ""
    
    def cleanup_file(self, file_path: str):
        """Delete temporary file (kept for compatibility)"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"🧹 Cleaned up temp file: {file_path}")
                if file_path in self.processed_files:
                    self.processed_files.remove(file_path)
        except Exception as e:
            logger.error(f"❌ Error cleaning up file {file_path}: {e}")
    
    def cleanup_all_files(self):
        """Clean up all tracked files (kept for compatibility)"""
        for file_path in self.processed_files.copy():
            self.cleanup_file(file_path)
        if self.processed_files:
            logger.info(f"🧹 Cleaned up {len(self.processed_files)} temporary files")
    
    async def cleanup_session(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            logger.debug("🔒 Closed aiohttp session")
    
    async def process_tweet_media_complete(self, media_objects: List[Any], tweet_id: str, api_url: str = None) -> Dict:
        """
        Complete media processing pipeline for a tweet using URL-based API
        
        Args:
            media_objects: List of media objects from tweepy
            tweet_id: Tweet ID
            api_url: API URL for processing media
            
        Returns:
            Dict with media info and descriptions
        """
        result = {
            'media_count': len(media_objects),
            'media_files': [],
            'descriptions': [],
            'combined_description': '',
            'errors': []
        }
        
        try:
            # Process media via URL-based API
            if api_url and media_objects:
                description = await self.process_media_from_tweet(media_objects, tweet_id, api_url)
                result['combined_description'] = description
                if description:
                    result['descriptions'] = description.split(' | ')
            
            # Generate basic media info without downloading
            for media in media_objects:
                media_info = {
                    'media_key': media.media_key,
                    'type': media.type,
                    'url': await self._get_media_url(media),
                    'width': getattr(media, 'width', None),
                    'height': getattr(media, 'height', None),
                    'duration_ms': getattr(media, 'duration_ms', None),
                    'alt_text': getattr(media, 'alt_text', None),
                    'tweet_id': tweet_id
                }
                result['media_files'].append(media_info)
            
            # Generate summary
            media_types = [m['type'] for m in result['media_files']]
            type_counts = {}
            for media_type in media_types:
                type_counts[media_type] = type_counts.get(media_type, 0) + 1
            
            result['summary'] = {
                'total_files': len(result['media_files']),
                'types': type_counts,
                'processed_count': len(result['descriptions'])
            }
            
        except Exception as e:
            error_msg = f"Error in complete media processing: {e}"
            logger.error(f"❌ {error_msg}")
            result['errors'].append(error_msg)
        
        return result
    
    def __del__(self):
        """Cleanup on destruction"""
        try:
            # Clean up files (if any)
            self.cleanup_all_files()
            
            # Close session if still open
            if hasattr(self, 'session') and self.session and not self.session.closed:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.cleanup_session())
                    else:
                        loop.run_until_complete(self.cleanup_session())
                except:
                    pass  # Best effort cleanup
        except:
            pass  # Ignore errors during cleanup


# Utility functions for easy integration
async def process_tweet_media_simple(media_objects: List[Any], tweet_id: str, api_url: str = None) -> str:
    """
    Simple function to process tweet media and return description using URL-based API
    
    Args:
        media_objects: List of media objects from tweepy response
        tweet_id: Tweet ID
        api_url: API URL for processing
    
    Returns:
        Combined description string
    """
    processor = MediaProcessor()
    try:
        return await processor.process_media_from_tweet(media_objects, tweet_id, api_url)
    finally:
        await processor.cleanup_session()


def get_media_summary(media_files: List[Dict]) -> str:
    """Generate a human-readable summary of media files"""
    if not media_files:
        return "No media"
    
    type_counts = {}
    
    for media in media_files:
        media_type = media.get('type', 'unknown')
        type_counts[media_type] = type_counts.get(media_type, 0) + 1
    
    # Format summary
    parts = []
    for media_type, count in type_counts.items():
        if count == 1:
            parts.append(f"1 {media_type}")
        else:
            parts.append(f"{count} {media_type}s")
    
    return ", ".join(parts)