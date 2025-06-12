# import os, pytz, re
# import time
# import logging
# import asyncio
# from fastapi import FastAPI
# from dotenv import load_dotenv
# import tweepy
# import requests
# from datetime import datetime, timedelta
# from media_processor import MediaProcessor
# import tempfile
# from datetime import datetime

# # Load env
# load_dotenv()
# IST = pytz.timezone('Asia/Kolkata')

# # Logging setup
# logging.basicConfig(level=logging.INFO,
#                     format="%(asctime)s %(levelname)s %(message)s",
#                     datefmt="%Y-%m-%d %H:%M:%S")
# logger = logging.getLogger(__name__)

# # Twitter API credentials
# TWITTER_API_KEY             = os.getenv("TWITTER_API_KEY")
# TWITTER_API_SECRET          = os.getenv("TWITTER_API_SECRET")
# TWITTER_ACCESS_TOKEN        = os.getenv("TWITTER_ACCESS_TOKEN")
# TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
# TWITTER_BEARER_TOKEN        = os.getenv("TWITTER_BEARER_TOKEN")
# BOT_USERNAME                = os.getenv("BOT_USERNAME", "").lower()
# CHECK_INTERVAL              = 900  # 15 minutes = 900 seconds
# LLM_API_URL                 = os.getenv("LLM_API_URL")
# MEDIA_API_URL               = os.getenv("MEDIA_API_URL")  # New: API for processing media to text
# DEFAULT_REPLY               = "Sorry, I can't answer right now."

# # Free tier limits (adjust as needed for testing)
# MAX_TWEETS_PER_POLL = 20  # Reduced for free tier
# DELAY_BETWEEN_REPLIES = 5  # Seconds between replies to avoid rate limits

# # Validate credentials
# required = [TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]
# if not all(required):
#     logger.error("Missing Twitter API credentials in .env")
#     raise SystemExit(1)
# if not BOT_USERNAME:
#     logger.error("BOT_USERNAME is required for mention detection")
#     raise SystemExit(1)
# if not LLM_API_URL:
#     logger.warning("LLM_API_URL not set; will use default replies.")
# if not MEDIA_API_URL:
#     logger.warning("MEDIA_API_URL not set; media processing will be disabled.")

# # Tweepy client - Free tier setup
# client = tweepy.Client(
#     bearer_token=TWITTER_BEARER_TOKEN,
#     consumer_key=TWITTER_API_KEY,
#     consumer_secret=TWITTER_API_SECRET,
#     access_token=TWITTER_ACCESS_TOKEN,
#     access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
#     wait_on_rate_limit=False  # We'll handle rate limits manually for better control
# )

# # Initialize media processor - create one instance and reuse it
# media_processor = MediaProcessor()

# # Track last processed IDs and startup time
# last_mention_id = None
# bot_start_time = datetime.utcnow()
# processed_tweet_ids = set()  # Keep track of processed tweets to avoid duplicates

# async def fetch_llm_response(question: str, thread_id: str, media_description: str = "") -> str:
#     """Fetch response from LLM API with error handling and media context"""
#     if not LLM_API_URL:
#         return DEFAULT_REPLY
    
#     try:
#         # Combine text question with media description
#         full_question = question
#         if media_description:
#             full_question = f"{question}\n\n[Media content: {media_description}]"
        
#         logger.info(f"Sending to LLM: {full_question[:100]}...")
        
#         params = {
#             "question": full_question, 
#             "thread_id": thread_id,
#             "using_Twitter": True
#         }
        
#         # Add media context as separate parameter if available
#         if media_description:
#             params["media_context"] = media_description
        
#         resp = requests.get(
#             LLM_API_URL, 
#             params=params, 
#             timeout=30
#         )
        
#         if resp.status_code == 200:
#             response_json = resp.json()
#             response_text = response_json.get("response", DEFAULT_REPLY)
#             logger.info(f"LLM response received: {len(response_text)} characters")
#             return response_text
#         else:
#             logger.error(f"LLM API returned status {resp.status_code}")
#     except requests.exceptions.Timeout:
#         logger.error("LLM request timed out")
#     except Exception as e:
#         logger.error(f"LLM request failed: {e}")
    
#     return DEFAULT_REPLY

# async def get_user_info(user_id: str) -> dict:
#     """Get user information from user ID with caching"""
#     try:
#         user = client.get_user(id=user_id)
#         if user.data:
#             return {
#                 "username": user.data.username,
#                 "name": user.data.name
#             }
#     except Exception as e:
#         logger.error(f"Failed to get user info for {user_id}: {e}")
    
#     return {
#         "username": f"user_{user_id}",
#         "name": "Unknown User"
#     }

# async def process_tweet_media(tweet_id: str, media_objects) -> str:
#     """Process media from tweet and return description using the global media processor"""
#     if not media_objects or not MEDIA_API_URL:
#         return ""
    
#     try:
#         logger.info(f"🖼️ Processing {len(media_objects)} media files from tweet {tweet_id}")
        
#         # Use the complete media processing pipeline
#         result = await media_processor.process_tweet_media_complete(
#             media_objects, 
#             tweet_id, 
#             MEDIA_API_URL
#         )
        
#         # Check for errors
#         if result.get('errors'):
#             logger.warning(f"⚠️ Media processing had errors: {result['errors']}")
        
#         media_description = result.get('combined_description', '')
        
#         if media_description:
#             logger.info(f"✅ Media processed successfully: {len(media_description)} chars from {result['summary']['processed_count']} files")
#             # Log media summary for debugging
#             summary = result.get('summary', {})
#             logger.info(f"📊 Media summary: {summary.get('total_files', 0)} files - {summary.get('types', {})}")
#             return media_description
#         else:
#             logger.warning("⚠️ No description returned from media processing")
#             return ""
            
#     except Exception as e:
#         logger.error(f"❌ Error processing media for tweet {tweet_id}: {e}")
#         return ""

# def extract_media_from_tweet_response(tweet, includes):
#     """Extract media objects from tweet response"""
#     media_objects = []
    
#     try:
#         # Check if tweet has media attachments
#         if hasattr(tweet, 'attachments') and tweet.attachments:
#             media_keys = tweet.attachments.get('media_keys', [])
            
#             # Get media objects from includes
#             if includes and 'media' in includes and media_keys:
#                 media_lookup = {media.media_key: media for media in includes['media']}
                
#                 for media_key in media_keys:
#                     if media_key in media_lookup:
#                         media_objects.append(media_lookup[media_key])
                
#                 logger.info(f"🖼️ Found {len(media_objects)} media files for tweet {tweet.id}")
        
#     except Exception as e:
#         logger.error(f"❌ Error extracting media from tweet {tweet.id}: {e}")
    
#     return media_objects

# async def poll_mentions():
#     """Poll for mentions every 15 minutes - Free tier optimized with media processing"""
#     global last_mention_id
    
#     logger.info(f"🚀 Starting mention polling (every {CHECK_INTERVAL/60} minutes)")
#     logger.info(f"Bot username: @{BOT_USERNAME}")
#     logger.info(f"Media processing: {'enabled' if MEDIA_API_URL else 'disabled'}")
    
#     # Wait before first poll
#     logger.info("Waiting 30 seconds before first mention poll...")
#     await asyncio.sleep(30)
    
#     # Search query - optimized for free tier
#     query = f"@{BOT_USERNAME} -is:retweet"

#     poll_count = 0
    
#     while True:
#         poll_count += 1
#         try:
#             logger.info(f"🔍 Poll #{poll_count}: Checking for new mentions...")
            
#             # Build search parameters for free tier
#             params = {
#                 "query": query,
#                 "max_results": MAX_TWEETS_PER_POLL,
#                 "tweet_fields": ["author_id", "created_at", "public_metrics", "attachments"],
#                 "user_fields": ["username"],
#                 "expansions": ["attachments.media_keys"],
#                 "media_fields": ["media_key", "type", "url", "variants", "width", "height", "duration_ms", "alt_text"]
#             }

#             # Use since_id only if we have processed tweets before
#             if last_mention_id:
#                 params["since_id"] = last_mention_id
            
#             try:
#                 resp = client.search_recent_tweets(**params)
#                 tweets = resp.data if resp.data else []
                
#             except tweepy.TooManyRequests as e:
#                 wait_time = int(e.response.headers.get("x-rate-limit-reset", time.time())) - time.time()
#                 wait_time = max(wait_time, 60)  # Ensure a minimum wait of 1 minute
#                 logger.warning(f"⚠️ Rate limit hit, sleeping for {wait_time//60} minutes...")
#                 await asyncio.sleep(wait_time)
#                 continue
#             except tweepy.Unauthorized:
#                 logger.error("❌ Authentication failed - check your credentials")
#                 await asyncio.sleep(300)
#                 continue
#             except Exception as e:
#                 logger.error(f"❌ Error searching tweets: {e}")
#                 await asyncio.sleep(60)
#                 continue

#             if not tweets:
#                 logger.info("✅ No new mentions found")
#             else:
#                 logger.info(f"📧 Found {len(tweets)} new mentions")
                
#                 # Process tweets in chronological order (oldest first)
#                 successful_replies = 0
#                 for tweet in reversed(tweets):
#                     try:
#                         # Skip if already processed
#                         if tweet.id in processed_tweet_ids:
#                             logger.info(f"⏭️ Skipping already processed tweet {tweet.id}")
#                             continue
                        
#                         # Update tracking
#                         last_mention_id = max(int(last_mention_id or 0), tweet.id)
#                         processed_tweet_ids.add(tweet.id)
                        
#                         # Skip old tweets (from before bot started)
#                         if tweet.created_at:
#                             tweet_time = tweet.created_at.replace(tzinfo=None)
#                             if tweet_time < bot_start_time:
#                                 logger.info(f"⏭️ Skipping old tweet {tweet.id}")
#                                 continue
                        
#                         # Extract question text

#                         # Remove all case-insensitive exact matches of the bot's username (e.g., @YourBot)
#                         text = re.sub(fr"\B@{re.escape(BOT_USERNAME)}\b", "", tweet.text, flags=re.IGNORECASE).strip()

#                         # Optional: clean up any extra spaces
#                         text = re.sub(r"\s+", " ", text).strip()
#                         if not text:
#                             text = "Hello!"
                        
#                         logger.info(f"📝 Processing tweet {tweet.id}: {text[:50]}...")
                        
#                         # Process media if present
#                         media_description = ""
#                         if MEDIA_API_URL:
#                             # Extract media objects from the response
#                             media_objects = extract_media_from_tweet_response(tweet, resp.includes)
                            
#                             if media_objects:
#                                 logger.info(f"🖼️ Found {len(media_objects)} media files in tweet {tweet.id}")
#                                 media_description = await process_tweet_media(str(tweet.id), media_objects)
#                             else:
#                                 logger.debug(f"📷 No media found in tweet {tweet.id}")
                        
#                         # Get user info
#                         user_info = await get_user_info(str(tweet.author_id))
#                         username = user_info["username"]
#                         author_id = str(tweet.author_id)
#                         timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')  # e.g., 20250605153245
#                         thread_id = f"{author_id}_{timestamp}"
#                         # Get LLM response with media context
#                         reply = await fetch_llm_response(text, thread_id, media_description)
                        
#                         # Ensure reply fits Twitter's character limit
#                         max_reply_length = 250  # Leave room for @username
#                         if len(reply) > max_reply_length:
#                             reply = reply[:max_reply_length-3] + "..."
                        
#                         # Create reply text
#                         reply_text = f"{reply}"
                        
#                         # Post reply
#                         try:
#                             response_tweet = client.create_tweet(
#                                 text=reply_text,
#                                 in_reply_to_tweet_id=tweet.id
#                             )
                            
#                             media_info = f" (with {len(media_description.split('|')) if media_description else 0} media descriptions)" if media_description else ""
#                             logger.info(f"✅ Successfully replied to @{username} (tweet {tweet.id}){media_info}")
#                             successful_replies += 1
                            
#                             # Delay between replies to avoid rate limits
#                             if DELAY_BETWEEN_REPLIES > 0:
#                                 await asyncio.sleep(DELAY_BETWEEN_REPLIES)
                                
#                         except tweepy.TooManyRequests:
#                             logger.warning("⚠️ Rate limit hit on tweet creation, skipping remaining tweets")
#                             break
#                         except tweepy.Forbidden as e:
#                             logger.error(f"🚫 Forbidden to reply to tweet {tweet.id}: {e}")
#                             continue
#                         except Exception as e:
#                             logger.error(f"❌ Error creating reply for tweet {tweet.id}: {e}")
#                             continue
                        
#                     except Exception as e:
#                         logger.error(f"❌ Error processing tweet {tweet.id}: {e}")
#                         continue
                
#                 logger.info(f"📊 Successfully replied to {successful_replies}/{len(tweets)} mentions")

#         except Exception as e:
#             logger.error(f"❌ Unexpected error in polling loop: {e}")
#             await asyncio.sleep(60)
        
#         # Clean up processed_tweet_ids periodically to prevent memory growth
#         if len(processed_tweet_ids) > 1000:
#             processed_tweet_ids.clear()
#             logger.info("🧹 Cleared processed tweet IDs cache")
        
#         # Wait for next poll cycle
#         next_poll_time = datetime.utcnow() + timedelta(seconds=CHECK_INTERVAL)
#         next_poll_time_ist = next_poll_time.astimezone(IST)

#         logger.info(f"💤 Sleeping until next poll at {next_poll_time_ist.strftime('%H:%M:%S')} ({CHECK_INTERVAL/60} minutes)")
#         await asyncio.sleep(CHECK_INTERVAL)

# # FastAPI app
# app = FastAPI(title="Twitter Bot with Media Processing", version="2.0.0")

# @app.on_event("startup")
# async def startup():
#     """Start the polling tasks"""
#     logger.info("🚀 Starting Twitter bot with media processing")
#     logger.info(f"Bot username: @{BOT_USERNAME}")
#     logger.info(f"Check interval: {CHECK_INTERVAL/60} minutes")
#     logger.info(f"Max tweets per poll: {MAX_TWEETS_PER_POLL}")
#     logger.info(f"LLM API URL: {LLM_API_URL}")
#     logger.info(f"Media API URL: {MEDIA_API_URL}")
#     logger.info("📝 Note: DM polling disabled (not available in free tier)")
    
#     # Test API connection
#     try:
#         me = client.get_me()
#         if me.data:
#             logger.info(f"✅ Successfully authenticated as @{me.data.username}")
#         else:
#             logger.error("❌ Authentication test failed")
#     except Exception as e:
#         logger.error(f"❌ Authentication test error: {e}")
    
#     # Start mention polling
#     asyncio.create_task(poll_mentions())

# @app.on_event("shutdown")
# async def shutdown():
#     """Cleanup on app shutdown"""
#     logger.info("🧹 Cleaning up media processor...")
#     media_processor.cleanup_all_files()
#     await media_processor.cleanup_session()

# @app.get("/")
# def root():
#     """Health check endpoint"""
#     return {
#         "status": "running",
#         "version": "2.0.0_with_media",
#         "bot_username": BOT_USERNAME,
#         "check_interval_minutes": CHECK_INTERVAL / 60,
#         "max_tweets_per_poll": MAX_TWEETS_PER_POLL,
#         "last_mention_id": last_mention_id,
#         "processed_tweets_count": len(processed_tweet_ids),
#         "started_at": bot_start_time.isoformat(),
#         "features": {
#             "mention_replies": True,
#             "dm_replies": False,
#             "rate_limit_handling": True,
#             "media_processing": bool(MEDIA_API_URL),
#             "media_temp_files": len(media_processor.processed_files)
#         }
#     }

# @app.get("/health")
# def health():
#     """Detailed health check"""
#     uptime = datetime.utcnow() - bot_start_time
#     return {
#         "status": "healthy",
#         "timestamp": datetime.utcnow().isoformat(),
#         "uptime_seconds": uptime.total_seconds(),
#         "uptime_human": str(uptime),
#         "last_mention_id": last_mention_id,
#         "api_limits": {
#             "tier": "free",
#             "max_tweets_per_poll": MAX_TWEETS_PER_POLL,
#             "delay_between_replies": DELAY_BETWEEN_REPLIES
#         },
#         "media_processor": {
#             "enabled": bool(MEDIA_API_URL),
#             "temp_files_count": len(media_processor.processed_files),
#             "temp_dir": str(media_processor.temp_dir)
#         }
#     }

# @app.get("/stats")
# def stats():
#     """Bot statistics"""
#     return {
#         "processed_tweets": len(processed_tweet_ids),
#         "last_mention_id": last_mention_id,
#         "bot_start_time": bot_start_time.isoformat(),
#         "next_poll_in_seconds": CHECK_INTERVAL,
#         "configuration": {
#             "bot_username": BOT_USERNAME,
#             "check_interval_minutes": CHECK_INTERVAL / 60,
#             "llm_api_configured": bool(LLM_API_URL),
#             "media_api_configured": bool(MEDIA_API_URL)
#         },
#         "media_stats": {
#             "temp_files_active": len(media_processor.processed_files),
#             "temp_directory": str(media_processor.temp_dir)
#         }
#     }

# @app.post("/cleanup-media")
# async def cleanup_media():
#     """Manual endpoint to cleanup media files"""
#     file_count = len(media_processor.processed_files)
#     media_processor.cleanup_all_files()
#     return {
#         "status": "success",
#         "message": f"Cleaned up {file_count} temporary media files"
#     }

# @app.get("/media-stats")
# def media_stats():
#     """Get detailed media processing statistics"""
#     return {
#         "media_processor": {
#             "temp_directory": str(media_processor.temp_dir),
#             "active_temp_files": len(media_processor.processed_files),
#             "session_active": media_processor.session is not None and not media_processor.session.closed if media_processor.session else False
#         },
#         "api_configuration": {
#             "media_api_url": MEDIA_API_URL,
#             "media_processing_enabled": bool(MEDIA_API_URL)
#         }
#     }

# if __name__ == "__main__":
#     import uvicorn
#     logger.info("Starting server...")
#     uvicorn.run(
#         app, 
#         host="0.0.0.0", 
#         port=int(os.getenv("PORT", 8000)), 
#         log_level="info"
#     )





import os, pytz, re
import time
import logging
import asyncio
from fastapi import FastAPI
from dotenv import load_dotenv
import tweepy
import requests
from datetime import datetime, timedelta
from media_processor import MediaProcessor
import tempfile

# Load env
load_dotenv()
IST = pytz.timezone('Asia/Kolkata')

# Logging setup
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Twitter API credentials
TWITTER_API_KEY             = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET          = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN        = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
TWITTER_BEARER_TOKEN        = os.getenv("TWITTER_BEARER_TOKEN")
BOT_USERNAME                = os.getenv("BOT_USERNAME", "").lower()
CHECK_INTERVAL              = 900  # 15 minutes = 900 seconds
LLM_API_URL                 = os.getenv("LLM_API_URL")
MEDIA_API_URL               = os.getenv("MEDIA_API_URL")
DEFAULT_REPLY               = "Sorry, I can't answer right now."

# Free tier limits
MAX_TWEETS_PER_POLL = 20
DELAY_BETWEEN_REPLIES = 5

# Validate credentials
required = [TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]
if not all(required):
    logger.error("Missing Twitter API credentials in .env")
    raise SystemExit(1)

# Tweepy client
client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=False
)

# Initialize media processor
media_processor = MediaProcessor()

# Track processed mentions
last_mention_id = None
bot_start_time = datetime.utcnow()
processed_tweet_ids = set()

async def get_conversation_context(mention_tweet_id: str, conversation_id: str) -> dict:
    """
    Enhanced function to get the original tweet and full conversation context
    when someone mentions the bot in a reply
    """
    context = {
        'original_tweet': None,
        'reply_chain': [],
        'media_content': [],
        'conversation_summary': ""
    }
    
    try:
        # Get the original tweet (root of conversation)
        if conversation_id:
            logger.info(f"🔍 Fetching original tweet {conversation_id} for context")
            
            original_response = client.get_tweet(
                id=conversation_id,
                expansions=["attachments.media_keys", "author_id"],
                media_fields=["media_key", "type", "url", "variants", "alt_text"],
                user_fields=["username", "name"],
                tweet_fields=["created_at", "public_metrics", "attachments"]
            )
            
            if original_response.data:
                original_tweet = original_response.data
                context['original_tweet'] = {
                    'id': original_tweet.id,
                    'text': original_tweet.text,
                    'author_id': original_tweet.author_id,
                    'created_at': original_tweet.created_at,
                    'media': []
                }
                
                # Extract media from original tweet
                if original_response.includes and 'media' in original_response.includes:
                    for media in original_response.includes['media']:
                        media_info = {
                            'type': media.type,
                            'url': getattr(media, 'url', None),
                            'alt_text': getattr(media, 'alt_text', None)
                        }
                        context['original_tweet']['media'].append(media_info)
                        context['media_content'].append(media)
                
                # Get author info
                if original_response.includes and 'users' in original_response.includes:
                    author = original_response.includes['users'][0]
                    context['original_tweet']['author'] = {
                        'username': author.username,
                        'name': author.name
                    }
                
                logger.info(f"✅ Found original tweet by @{context['original_tweet'].get('author', {}).get('username', 'unknown')}")
        
        # Get recent replies in the conversation for additional context
        try:
            conversation_search = client.search_recent_tweets(
                query=f"conversation_id:{conversation_id}",
                max_results=10,
                tweet_fields=["author_id", "created_at", "in_reply_to_user_id"],
                user_fields=["username"],
                expansions=["author_id"]
            )
            
            if conversation_search.data:
                context['reply_chain'] = []
                for reply in conversation_search.data:
                    reply_info = {
                        'id': reply.id,
                        'text': reply.text,
                        'author_id': reply.author_id,
                        'created_at': reply.created_at
                    }
                    context['reply_chain'].append(reply_info)
                
                logger.info(f"📝 Found {len(context['reply_chain'])} replies in conversation")
        
        except Exception as e:
            logger.warning(f"⚠️ Could not fetch conversation replies: {e}")
    
    except Exception as e:
        logger.error(f"❌ Error getting conversation context: {e}")
    
    return context

# async def build_llm_context(mention_text: str, conversation_context: dict, media_description: str = "") -> str:
#     """
#     Build comprehensive context for LLM including original tweet, conversation, and media
#     """
#     context_parts = []
    
#     # Add original tweet context
#     if conversation_context.get('original_tweet'):
#         original = conversation_context['original_tweet']
#         author_info = original.get('author', {})
#         author_name = author_info.get('username', 'unknown')
        
#         context_parts.append(f"ORIGINAL TWEET by @{author_name}:")
#         context_parts.append(f'"{original["text"]}"')
        
#         if original.get('media'):
#             context_parts.append(f"[Original tweet has {len(original['media'])} media files]")
    
#     # Add conversation flow if there are replies
#     if conversation_context.get('reply_chain') and len(conversation_context['reply_chain']) > 1:
#         context_parts.append(f"\nCONVERSATION CONTEXT ({len(conversation_context['reply_chain'])} replies):")
#         for i, reply in enumerate(conversation_context['reply_chain'][-3:]):  # Last 3 replies
#             context_parts.append(f"Reply {i+1}: {reply['text'][:100]}...")
    
#     # Add media description
#     if media_description:
#         context_parts.append(f"\nMEDIA CONTENT: {media_description}")
    
#     # Add the mention that triggered the bot
#     context_parts.append(f"\nUSER MENTIONED BOT: {mention_text}")
#     context_parts.append("\nPlease provide a helpful and contextual reply that addresses the user's request while considering the original tweet and conversation context.")
    
#     return "\n".join(context_parts)
async def build_llm_context(mention_text: str, conversation_context: dict, media_description: str = "") -> str:
    """
    Build minimal LLM context: original tweet, media (if any), and user mention.
    """
    context_parts = []
    
    # Add original tweet
    if conversation_context.get('original_tweet'):
        original = conversation_context['original_tweet']
        print(f"Original tweet found: {original['text']}...")  # Debug log
        author_info = original.get('author', {})
        author_name = author_info.get('username', 'unknown')
        
        # context_parts.append(f"ORIGINAL TWEET by @{author_name}:")
        context_parts.append(f'"{original["text"]}"')
        
        if original.get('media'):
            context_parts.append(f"[Original tweet has {len(original['media'])} media files]")

    # Add media description if provided
    if media_description:
        context_parts.append(f"\nMEDIA CONTENT: {media_description}")

    # Add the mention that triggered the bot
    context_parts.append(f"\nUSER MENTIONED BOT: {mention_text}")

    return "\n".join(context_parts)

async def fetch_llm_response_enhanced(mention_text: str, thread_id: str, conversation_context: dict, media_description: str = "") -> str:
    """Enhanced LLM response with full conversation context"""
    if not LLM_API_URL:
        return DEFAULT_REPLY
    
    try:
        # Build comprehensive context
        full_context = await build_llm_context(mention_text, conversation_context, media_description)
        print(f"Full context for LLM:\n{full_context}")  # Log first 500 chars for debugging
        logger.info(f"📤 Sending enhanced context to LLM ({len(full_context)} chars)")
        
        params = {
            "question": full_context,
            "thread_id": thread_id,
            "using_Twitter": True,
            "context_type": "conversation_reply"
        }
        
        # Add conversation metadata
        if conversation_context.get('original_tweet'):
            params["original_tweet_id"] = conversation_context['original_tweet']['id']
            params["conversation_id"] = conversation_context['original_tweet']['id']
        
        resp = requests.get(LLM_API_URL, params=params, timeout=100)
        
        if resp.status_code == 200:
            response_json = resp.json()
            response_text = response_json.get("response", DEFAULT_REPLY)
            logger.info(f"✅ Enhanced LLM response received: {len(response_text)} characters")
            return response_text
        else:
            logger.error(f"❌ LLM API returned status {resp.status_code}")
    
    except requests.exceptions.Timeout:
        logger.error("⏰ LLM request timed out")
    except Exception as e:
        logger.error(f"❌ Enhanced LLM request failed: {e}")
    
    return DEFAULT_REPLY

async def process_mention_with_context(tweet, resp_includes):
    """
    Enhanced mention processing that gets full conversation context
    """
    try:
        tweet_id = str(tweet.id)
        
        # Skip if already processed
        if tweet.id in processed_tweet_ids:
            logger.info(f"⏭️ Skipping already processed tweet {tweet_id}")
            return False
        
        # Add to processed set
        processed_tweet_ids.add(tweet.id)
        
        # Extract mention text (remove bot username)
        mention_text = re.sub(fr"\B@{re.escape(BOT_USERNAME)}\b", "", tweet.text, flags=re.IGNORECASE).strip()
        mention_text = re.sub(r"\s+", " ", mention_text).strip()
        if not mention_text:
            mention_text = "Hello!"
        
        logger.info(f"📝 Processing mention {tweet_id}: {mention_text[:50]}...")
        
        # Get conversation context (this is the key enhancement!)
        conversation_id = getattr(tweet, 'conversation_id', None) or tweet_id
        conversation_context = await get_conversation_context(tweet_id, conversation_id)
        
        # Process media from the mention tweet itself
        media_description = ""
        if MEDIA_API_URL:
            media_objects = extract_media_from_tweet_response(tweet, resp_includes)
            if media_objects:
                logger.info(f"🖼️ Processing {len(media_objects)} media files from mention")
                media_description = await process_tweet_media(tweet_id, media_objects)
            
            # Also process media from original tweet if present
            if conversation_context.get('media_content'):
                logger.info(f"🖼️ Processing {len(conversation_context['media_content'])} media files from original tweet")
                original_media_desc = await process_tweet_media(
                    str(conversation_context['original_tweet']['id']), 
                    conversation_context['media_content']
                )
                if original_media_desc:
                    media_description = f"{media_description}\n[Original tweet media: {original_media_desc}]" if media_description else f"[Original tweet media: {original_media_desc}]"
        
        # Get user info
        user_info = await get_user_info(str(tweet.author_id))
        username = user_info["username"]
        
        # Create thread ID
        author_id = str(tweet.author_id)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        thread_id = f"{author_id}_{timestamp}"
        
        # Get enhanced LLM response with full context
        reply = await fetch_llm_response_enhanced(
            mention_text, 
            thread_id, 
            conversation_context, 
            media_description
        )
        
        # Ensure reply fits Twitter's character limit
        max_reply_length = 250
        if len(reply) > max_reply_length:
            reply = reply[:max_reply_length-3] + "..."
        
        # Post reply
        try:
            response_tweet = client.create_tweet(
                text=reply,
                in_reply_to_tweet_id=tweet.id
            )
            
            # Log success with context info
            context_info = ""
            if conversation_context.get('original_tweet'):
                orig_author = conversation_context['original_tweet'].get('author', {}).get('username', 'unknown')
                context_info = f" (replying to conversation started by @{orig_author})"
            
            media_info = f" with media context" if media_description else ""
            logger.info(f"✅ Successfully replied to @{username}{context_info}{media_info}")
            
            return True
            
        except tweepy.TooManyRequests:
            logger.warning("⚠️ Rate limit hit on tweet creation")
            return False
        except Exception as e:
            logger.error(f"❌ Error creating reply: {e}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Error processing mention {tweet_id}: {e}")
        return False

def extract_media_from_tweet_response(tweet, includes):
    """Extract media objects from tweet response"""
    media_objects = []
    
    try:
        if hasattr(tweet, 'attachments') and tweet.attachments:
            media_keys = tweet.attachments.get('media_keys', [])
            
            if includes and 'media' in includes and media_keys:
                media_lookup = {media.media_key: media for media in includes['media']}
                
                for media_key in media_keys:
                    if media_key in media_lookup:
                        media_objects.append(media_lookup[media_key])
                
                logger.info(f"🖼️ Found {len(media_objects)} media files")
    
    except Exception as e:
        logger.error(f"❌ Error extracting media: {e}")
    
    return media_objects

async def process_tweet_media(tweet_id: str, media_objects) -> str:
    """Process media from tweet and return description"""
    if not media_objects or not MEDIA_API_URL:
        return ""
    
    try:
        logger.info(f"🖼️ Processing {len(media_objects)} media files from tweet {tweet_id}")
        
        result = await media_processor.process_tweet_media_complete(
            media_objects, 
            tweet_id, 
            MEDIA_API_URL
        )
        
        if result.get('errors'):
            logger.warning(f"⚠️ Media processing had errors: {result['errors']}")
        
        media_description = result.get('combined_description', '')
        
        if media_description:
            logger.info(f"✅ Media processed successfully: {len(media_description)} chars")
            return media_description
        else:
            logger.warning("⚠️ No description returned from media processing")
            return ""
            
    except Exception as e:
        logger.error(f"❌ Error processing media: {e}")
        return ""

async def get_user_info(user_id: str) -> dict:
    """Get user information from user ID"""
    try:
        user = client.get_user(id=user_id)
        if user.data:
            return {
                "username": user.data.username,
                "name": user.data.name
            }
    except Exception as e:
        logger.error(f"Failed to get user info for {user_id}: {e}")
    
    return {
        "username": f"user_{user_id}",
        "name": "Unknown User"
    }

async def poll_mentions():
    """Enhanced mention polling with conversation context"""
    global last_mention_id
    
    logger.info(f"🚀 Starting enhanced mention polling (every {CHECK_INTERVAL/60} minutes)")
    logger.info(f"Bot username: @{BOT_USERNAME}")
    logger.info("✨ Enhanced features: Conversation context, Original tweet analysis, Full media processing")
    
    await asyncio.sleep(30)  # Initial wait
    
    query = f"@{BOT_USERNAME} -is:retweet"
    poll_count = 0
    
    while True:
        poll_count += 1
        try:
            logger.info(f"🔍 Enhanced Poll #{poll_count}: Checking for mentions with conversation context...")
            
            params = {
                "query": query,
                "max_results": MAX_TWEETS_PER_POLL,
                "tweet_fields": ["author_id", "created_at", "conversation_id", "in_reply_to_user_id", "attachments"],
                "user_fields": ["username", "name"],
                "expansions": ["attachments.media_keys", "author_id"],
                "media_fields": ["media_key", "type", "url", "variants", "alt_text"]
            }
            
            if last_mention_id:
                params["since_id"] = last_mention_id
            
            try:
                resp = client.search_recent_tweets(**params)
                tweets = resp.data if resp.data else []
                
            except tweepy.TooManyRequests as e:
                wait_time = int(e.response.headers.get("x-rate-limit-reset", time.time())) - time.time()
                wait_time = max(wait_time, 60)
                logger.warning(f"⚠️ Rate limit hit, sleeping for {wait_time//60} minutes...")
                await asyncio.sleep(wait_time)
                continue
            except Exception as e:
                logger.error(f"❌ Error searching tweets: {e}")
                await asyncio.sleep(60)
                continue

            if not tweets:
                logger.info("✅ No new mentions found")
            else:
                logger.info(f"📧 Found {len(tweets)} new mentions - processing with conversation context")
                
                successful_replies = 0
                for tweet in reversed(tweets):  # Process oldest first
                    # Update last_mention_id
                    last_mention_id = max(int(last_mention_id or 0), tweet.id)
                    
                    # Skip old tweets
                    if tweet.created_at and tweet.created_at.replace(tzinfo=None) < bot_start_time:
                        logger.info(f"⏭️ Skipping old tweet {tweet.id}")
                        continue
                    
                    # Process with enhanced context
                    success = await process_mention_with_context(tweet, resp.includes)
                    if success:
                        successful_replies += 1
                        
                        # Rate limit delay
                        if DELAY_BETWEEN_REPLIES > 0:
                            await asyncio.sleep(DELAY_BETWEEN_REPLIES)
                
                logger.info(f"📊 Successfully processed {successful_replies}/{len(tweets)} mentions with context")

        except Exception as e:
            logger.error(f"❌ Unexpected error in enhanced polling loop: {e}")
            await asyncio.sleep(60)
        
        # Cleanup
        if len(processed_tweet_ids) > 1000:
            processed_tweet_ids.clear()
            logger.info("🧹 Cleared processed tweet IDs cache")
        
        # Wait for next poll
        next_poll_time = datetime.utcnow() + timedelta(seconds=CHECK_INTERVAL)
        next_poll_time_ist = next_poll_time.astimezone(IST)
        logger.info(f"💤 Sleeping until next enhanced poll at {next_poll_time_ist.strftime('%H:%M:%S')}")
        await asyncio.sleep(CHECK_INTERVAL)

# FastAPI app remains the same...
app = FastAPI(title="Enhanced Twitter Bot with Conversation Context", version="3.0.0")

@app.on_event("startup")
async def startup():
    """Start the polling tasks"""
    logger.info("🚀 Starting Twitter bot with media processing")
    logger.info(f"Bot username: @{BOT_USERNAME}")
    logger.info(f"Check interval: {CHECK_INTERVAL/60} minutes")
    logger.info(f"Max tweets per poll: {MAX_TWEETS_PER_POLL}")
    logger.info(f"LLM API URL: {LLM_API_URL}")
    logger.info(f"Media API URL: {MEDIA_API_URL}")
    logger.info("📝 Note: DM polling disabled (not available in free tier)")
    
    # Test API connection
    try:
        me = client.get_me()
        if me.data:
            logger.info(f"✅ Successfully authenticated as @{me.data.username}")
        else:
            logger.error("❌ Authentication test failed")
    except Exception as e:
        logger.error(f"❌ Authentication test error: {e}")
    
    # Start mention polling
    asyncio.create_task(poll_mentions())

@app.get("/")
def root():
    return {
        "status": "running",
        "version": "3.0.0_enhanced_context",
        "features": {
            "conversation_context": True,
            "original_tweet_analysis": True,
            "enhanced_media_processing": True,
            "mention_replies": True
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))