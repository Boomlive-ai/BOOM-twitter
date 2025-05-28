import os
import time
import logging
import asyncio
import hmac
import hashlib
import base64
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import tweepy
import requests
from typing import Dict, List, Optional

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Twitter API credentials
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# Bot configuration
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()
BOT_USER_ID = os.getenv("BOT_USER_ID")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "your_webhook_secret_here")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Your public webhook URL

# LLM configuration
LLM_API_URL = os.getenv("LLM_API_URL")
DEFAULT_REPLY = "Sorry, I can't answer right now. Please try again later."

# Bot behavior settings
REPLY_TO_MENTIONS = os.getenv("REPLY_TO_MENTIONS", "true").lower() == "true"
REPLY_TO_DMS = os.getenv("REPLY_TO_DMS", "true").lower() == "true"
MAX_REPLY_LENGTH = int(os.getenv("MAX_REPLY_LENGTH", "280"))
AUTO_FOLLOW_BACK = os.getenv("AUTO_FOLLOW_BACK", "false").lower() == "true"

# Rate limiting settings (for Basic tier)
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "900"))  # 15 minutes
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "300"))

# Validate required credentials
required_creds = [
    TWITTER_API_KEY, TWITTER_API_SECRET, 
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET, 
    TWITTER_BEARER_TOKEN
]

if not all(required_creds):
    logger.error("Missing required Twitter API credentials")
    raise SystemExit(1)

if not BOT_USERNAME:
    logger.error("BOT_USERNAME is required")
    raise SystemExit(1)

# Initialize Twitter clients
try:
    # v2 API client
    client_v2 = tweepy.Client(
        bearer_token=TWITTER_BEARER_TOKEN,
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True
    )
    
    # v1.1 API for DMs and some other features
    auth_v1 = tweepy.OAuth1UserHandler(
        TWITTER_API_KEY, TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
    )
    client_v1 = tweepy.API(auth_v1, wait_on_rate_limit=True)
    
    logger.info("Twitter clients initialized successfully")
    
except Exception as e:
    logger.error(f"Failed to initialize Twitter clients: {e}")
    raise SystemExit(1)

# Rate limiting tracker
rate_limit_tracker = {
    "requests": [],
    "last_reset": time.time()
}

# Response cache to avoid duplicate replies
response_cache = {}
CACHE_DURATION = 3600  # 1 hour

class TwitterBot:
    def __init__(self):
        self.processed_tweets = set()
        self.processed_dms = set()
        self.start_time = datetime.now()
        
    def is_rate_limited(self) -> bool:
        """Check if we're hitting rate limits"""
        current_time = time.time()
        
        # Clean old requests
        cutoff_time = current_time - RATE_LIMIT_WINDOW
        rate_limit_tracker["requests"] = [
            req_time for req_time in rate_limit_tracker["requests"] 
            if req_time > cutoff_time
        ]
        
        # Check if we're over the limit
        return len(rate_limit_tracker["requests"]) >= RATE_LIMIT_REQUESTS
    
    def record_request(self):
        """Record a new API request"""
        rate_limit_tracker["requests"].append(time.time())
    
    async def get_llm_response(self, question: str, context: str = "") -> str:
        """Get response from LLM API"""
        try:
            # Check cache first
            cache_key = f"{question}_{context}"
            if cache_key in response_cache:
                cache_entry = response_cache[cache_key]
                if time.time() - cache_entry["timestamp"] < CACHE_DURATION:
                    logger.info("Using cached response")
                    return cache_entry["response"]
            
            # Make API request
            params = {
                "question": question,
                "thread_id": context
            }
            
            response = requests.get(LLM_API_URL, params=params, timeout=15)
            
            if response.status_code == 200:
                llm_response = response.text.strip()
                
                # Cache the response
                response_cache[cache_key] = {
                    "response": llm_response,
                    "timestamp": time.time()
                }
                
                # Clean old cache entries
                self.clean_cache()
                
                return llm_response
            else:
                logger.warning(f"LLM API returned status {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error("LLM API request timed out")
        except Exception as e:
            logger.error(f"LLM API request failed: {e}")
        
        return DEFAULT_REPLY
    
    def clean_cache(self):
        """Clean expired cache entries"""
        current_time = time.time()
        expired_keys = [
            key for key, value in response_cache.items()
            if current_time - value["timestamp"] > CACHE_DURATION
        ]
        for key in expired_keys:
            del response_cache[key]
    
    async def handle_mention(self, tweet_data: dict, user_data: dict = None):
        """Handle incoming mention"""
        try:
            tweet_id = tweet_data.get("id")
            author_id = tweet_data.get("author_id")
            text = tweet_data.get("text", "")
            
            # Skip if already processed
            if tweet_id in self.processed_tweets:
                return
            
            self.processed_tweets.add(tweet_id)
            
            # Skip if it's our own tweet
            if author_id == BOT_USER_ID:
                return
            
            # Skip if rate limited
            if self.is_rate_limited():
                logger.warning("Rate limited, skipping mention")
                return
            
            logger.info(f"Processing mention {tweet_id}")
            
            # Get username
            username = "friend"
            if user_data:
                for user in user_data:
                    if user.get("id") == author_id:
                        username = user.get("username", "friend")
                        break
            
            # Extract question
            question = text.replace(f"@{BOT_USERNAME}", "").strip()
            if not question:
                question = "Hello!"
            
            # Get LLM response
            response = await self.get_llm_response(
                question, 
                f"mention_{author_id}"
            )
            
            # Truncate if necessary
            max_length = MAX_REPLY_LENGTH - len(f"@{username} ") - 10
            if len(response) > max_length:
                response = response[:max_length-3] + "..."
            
            # Reply
            reply_text = f"@{username} {response}"
            
            try:
                client_v2.create_tweet(
                    text=reply_text,
                    in_reply_to_tweet_id=tweet_id
                )
                self.record_request()
                logger.info(f"Replied to mention from @{username}")
                
            except Exception as e:
                logger.error(f"Failed to reply to mention: {e}")
                
        except Exception as e:
            logger.error(f"Error handling mention: {e}")
    
    async def handle_dm(self, dm_data: dict):
        """Handle incoming direct message"""
        try:
            dm_id = dm_data.get("id")
            sender_id = dm_data.get("sender_id")
            text = dm_data.get("text", "")
            
            # Skip if already processed
            if dm_id in self.processed_dms:
                return
            
            self.processed_dms.add(dm_id)
            
            # Skip if it's from us
            if sender_id == BOT_USER_ID:
                return
            
            # Skip if rate limited
            if self.is_rate_limited():
                logger.warning("Rate limited, skipping DM")
                return
            
            logger.info(f"Processing DM {dm_id}")
            
            # Get response
            question = text.strip() or "Hello!"
            response = await self.get_llm_response(
                question,
                f"dm_{sender_id}"
            )
            
            # Truncate if necessary (DMs can be longer)
            if len(response) > 10000:
                response = response[:9997] + "..."
            
            # Reply via DM
            try:
                client_v1.send_direct_message(
                    recipient_id=sender_id,
                    text=response
                )
                self.record_request()
                logger.info(f"Replied to DM from {sender_id}")
                
            except Exception as e:
                logger.error(f"Failed to reply to DM: {e}")
                
        except Exception as e:
            logger.error(f"Error handling DM: {e}")
    
    async def handle_follow(self, follow_data: dict):
        """Handle new follower (auto-follow back if enabled)"""
        try:
            if not AUTO_FOLLOW_BACK:
                return
            
            follower_id = follow_data.get("id")
            
            if follower_id and follower_id != BOT_USER_ID:
                try:
                    client_v2.follow_user(follower_id)
                    self.record_request()
                    logger.info(f"Auto-followed user {follower_id}")
                except Exception as e:
                    logger.error(f"Failed to auto-follow user {follower_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error handling follow: {e}")

# Initialize bot
bot = TwitterBot()

# FastAPI app
app = FastAPI(
    title="Twitter Bot Webhook",
    description="Production-ready Twitter bot with webhook support",
    version="2.0.0"
)

def verify_twitter_signature(payload: bytes, signature: str) -> bool:
    """Verify Twitter webhook signature"""
    if not signature:
        return False
    
    try:
        expected_signature = hmac.new(
            TWITTER_API_SECRET.encode(),
            payload,
            hashlib.sha256
        ).digest()
        expected_signature = base64.b64encode(expected_signature).decode()
        
        return hmac.compare_digest(signature, f"sha256={expected_signature}")
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False

@app.get("/webhook/twitter")
async def twitter_webhook_challenge(crc_token: str):
    """Handle Twitter webhook CRC challenge"""
    try:
        signature = hmac.new(
            TWITTER_API_SECRET.encode(),
            crc_token.encode(),
            hashlib.sha256
        ).digest()
        
        response_token = base64.b64encode(signature).decode()
        
        logger.info("Webhook CRC challenge completed")
        return {"response_token": f"sha256={response_token}"}
        
    except Exception as e:
        logger.error(f"CRC challenge failed: {e}")
        raise HTTPException(status_code=500, detail="CRC challenge failed")

@app.post("/webhook/twitter")
async def twitter_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle Twitter webhook events"""
    try:
        # Get raw body for signature verification
        body = await request.body()
        signature = request.headers.get("x-twitter-webhooks-signature")
        
        # Verify signature in production
        if WEBHOOK_SECRET != "your_webhook_secret_here":
            if not verify_twitter_signature(body, signature):
                logger.warning("Invalid webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse JSON data
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Handle different event types
        if "tweet_create_events" in data:
            for tweet in data["tweet_create_events"]:
                # Check if it's a mention
                if f"@{BOT_USERNAME}" in tweet.get("text", "").lower():
                    if REPLY_TO_MENTIONS:
                        background_tasks.add_task(
                            bot.handle_mention,
                            tweet,
                            data.get("users", [])
                        )
        
        if "direct_message_events" in data:
            for dm in data["direct_message_events"]:
                if dm.get("type") == "message_create":
                    if REPLY_TO_DMS:
                        background_tasks.add_task(
                            bot.handle_dm,
                            dm.get("message_create", {})
                        )
        
        if "follow_events" in data:
            for follow in data["follow_events"]:
                background_tasks.add_task(bot.handle_follow, follow)
        
        return {"status": "ok", "processed": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
async def root():
    """Health check and bot status"""
    uptime = datetime.now() - bot.start_time
    
    return {
        "status": "running",
        "mode": "webhook",
        "bot_username": BOT_USERNAME,
        "uptime_seconds": int(uptime.total_seconds()),
        "features": {
            "mentions": REPLY_TO_MENTIONS,
            "dms": REPLY_TO_DMS,
            "auto_follow": AUTO_FOLLOW_BACK
        },
        "rate_limit": {
            "requests_in_window": len(rate_limit_tracker["requests"]),
            "window_seconds": RATE_LIMIT_WINDOW,
            "max_requests": RATE_LIMIT_REQUESTS
        }
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    try:
        # Test API connectivity
        me = client_v2.get_me()
        api_status = "healthy" if me.data else "degraded"
    except Exception as e:
        api_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_status": api_status,
        "cache_size": len(response_cache),
        "processed_tweets": len(bot.processed_tweets),
        "processed_dms": len(bot.processed_dms)
    }

@app.get("/stats")
async def stats():
    """Bot statistics"""
    uptime = datetime.now() - bot.start_time
    
    return {
        "uptime": {
            "seconds": int(uptime.total_seconds()),
            "human": str(uptime).split('.')[0]
        },
        "processing": {
            "tweets_processed": len(bot.processed_tweets),
            "dms_processed": len(bot.processed_dms),
            "cache_entries": len(response_cache)
        },
        "rate_limiting": {
            "current_window_requests": len(rate_limit_tracker["requests"]),
            "window_duration_seconds": RATE_LIMIT_WINDOW,
            "max_requests_per_window": RATE_LIMIT_REQUESTS,
            "rate_limited": bot.is_rate_limited()
        },
        "configuration": {
            "reply_to_mentions": REPLY_TO_MENTIONS,
            "reply_to_dms": REPLY_TO_DMS,
            "auto_follow_back": AUTO_FOLLOW_BACK,
            "max_reply_length": MAX_REPLY_LENGTH
        }
    }

@app.post("/webhook/setup")
async def setup_webhook():
    """Setup webhook with Twitter (requires WEBHOOK_URL in env)"""
    if not WEBHOOK_URL:
        raise HTTPException(
            status_code=400, 
            detail="WEBHOOK_URL not configured"
        )
    
    try:
        # This would typically use Twitter's webhook management API
        # Implementation depends on your specific setup
        
        webhook_url = f"{WEBHOOK_URL}/webhook/twitter"
        
        return {
            "status": "setup_required",
            "webhook_url": webhook_url,
            "instructions": [
                "1. Register webhook URL in Twitter Developer Portal",
                "2. Set up webhook environment",
                "3. Subscribe to webhook events",
                "4. Test with CRC challenge"
            ]
        }
        
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Cleanup task
@app.on_event("startup")
async def startup():
    """Initialize bot on startup"""
    logger.info("Twitter Webhook Bot starting up...")
    logger.info(f"Bot username: @{BOT_USERNAME}")
    logger.info(f"Reply to mentions: {REPLY_TO_MENTIONS}")
    logger.info(f"Reply to DMs: {REPLY_TO_DMS}")
    logger.info(f"Auto follow back: {AUTO_FOLLOW_BACK}")
    
    # Clean cache periodically
    async def cleanup_task():
        while True:
            await asyncio.sleep(3600)  # Every hour
            bot.clean_cache()
            logger.info("Cache cleanup completed")
    
    asyncio.create_task(cleanup_task())

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    logger.info("Twitter Webhook Bot shutting down...")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting webhook bot on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,  # Don't use reload in production
        access_log=True
    )