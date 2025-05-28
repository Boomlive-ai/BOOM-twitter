# import os
# import time
# import logging
# import requests
# import tweepy
# import asyncio
# from fastapi import FastAPI, BackgroundTasks
# from dotenv import load_dotenv

# # ─── Configuration ────────────────────────────────────────────────────────────
# load_dotenv()  # loads .env into os.environ

# # Twitter API credentials
# TWITTER_API_KEY            = os.getenv("TWITTER_API_KEY")
# TWITTER_API_SECRET         = os.getenv("TWITTER_API_SECRET")
# TWITTER_ACCESS_TOKEN       = os.getenv("TWITTER_ACCESS_TOKEN")
# TWITTER_ACCESS_TOKEN_SECRET= os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
# TWITTER_BEARER_TOKEN       = os.getenv("TWITTER_BEARER_TOKEN")
# TWITTER_USERNAME           = os.getenv("TWITTER_USERNAME")

# # Your hosted LLM endpoint
# LLM_API_URL                = os.getenv("LLM_API_URL", "https://a8c4cosco0wc0gg8s40w8kco.vps.boomlive.in/query")

# # How often to poll (in seconds)
# CHECK_INTERVAL             = int(os.getenv("CHECK_INTERVAL", 30))

# # Fallback reply if LLM fails
# DEFAULT_REPLY_MESSAGE      = os.getenv("DEFAULT_REPLY_MESSAGE", "Sorry, I'm having trouble answering right now. Please try again later!")

# # ─── Logging Setup ────────────────────────────────────────────────────────────
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S"
# )
# logger = logging.getLogger(__name__)

# # ─── Twitter Client ──────────────────────────────────────────────────────────
# class TwitterClient:
#     def __init__(self):
#         self.client = tweepy.Client(
#             bearer_token=TWITTER_BEARER_TOKEN,
#             consumer_key=TWITTER_API_KEY,
#             consumer_secret=TWITTER_API_SECRET,
#             access_token=TWITTER_ACCESS_TOKEN,
#             access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
#             wait_on_rate_limit=True
#         )
#         me = self.client.get_me().data
#         self.user_id = me.id
#         logger.info(f"Bot running as @{TWITTER_USERNAME} (ID: {self.user_id})")

#     def get_mentions(self, since_id=None, max_results=10):
#         query = f"@{TWITTER_USERNAME} -is:retweet"
#         params = {"query": query, "max_results": max_results}
#         if since_id:
#             params["since_id"] = since_id
#         resp = self.client.search_recent_tweets(**params)
#         return resp.data or []

#     def reply_to_tweet(self, tweet_id, text):
#         try:
#             self.client.create_tweet(
#                 text=text,
#                 in_reply_to_tweet_id=tweet_id
#             )
#             logger.info(f"Replied to tweet {tweet_id}")
#         except Exception as e:
#             logger.error(f"Failed to reply to {tweet_id}: {e}")

# # ─── Query (LLM) Client ───────────────────────────────────────────────────────
# class QueryClient:
#     def __init__(self, api_url=LLM_API_URL):
#         self.api_url = api_url

#     def get_response(self, question, thread_id, max_retries=3, retry_delay=2):
#         params = {"question": question, "thread_id": thread_id}
#         attempt = 0
#         while attempt < max_retries:
#             try:
#                 r = requests.get(self.api_url, params=params, timeout=10)
#                 if r.status_code == 200:
#                     return r.text.strip()
#                 elif 500 <= r.status_code < 600:
#                     logger.warning(f"Server error {r.status_code}, retrying...")
#                     attempt += 1
#                     time.sleep(retry_delay)
#                     continue
#                 else:
#                     logger.error(f"LLM API error {r.status_code}: {r.text}")
#                     return None
#             except requests.RequestException as e:
#                 logger.error(f"Request failed: {e}")
#                 attempt += 1
#                 time.sleep(retry_delay)
#         return None

# # ─── FastAPI Setup ────────────────────────────────────────────────────────────
# app = FastAPI(title="Twitter Reply Bot")

# # Clients and state
# twitter_client = TwitterClient()
# query_client = QueryClient()
# last_mention_id = None
# running = False

# @app.on_event("startup")
# async def startup_event():
#     global running, last_mention_id
#     # Prime on first run
#     mentions = twitter_client.get_mentions()
#     if mentions:
#         last_mention_id = mentions[0].id
#         logger.info(f"Initialized last_mention_id = {last_mention_id}")
#     running = True
#     # Launch background task
#     asyncio.create_task(check_mentions_periodically())

# @app.on_event("shutdown")
# async def shutdown_event():
#     global running
#     running = False
#     logger.info("Shutting down background task")

# async def check_mentions_periodically():
#     global last_mention_id, running
#     while running:
#         mentions = twitter_client.get_mentions(since_id=last_mention_id)
#         if mentions:
#             for tweet in mentions:
#                 last_mention_id = max(int(last_mention_id or 0), int(tweet.id))
#                 question = tweet.text.replace(f"@{TWITTER_USERNAME}", "").strip()
#                 if not question:
#                     reply = DEFAULT_REPLY_MESSAGE
#                 else:
#                     thread_id = str(tweet.author_id)
#                     resp = query_client.get_response(question, thread_id)
#                     reply = resp[:280] if resp else DEFAULT_REPLY_MESSAGE
#                 twitter_client.reply_to_tweet(tweet.id, reply)
#         await asyncio.sleep(CHECK_INTERVAL)

# @app.get("/")
# def read_root():
#     return {"status": "running", "last_mention_id": last_mention_id}

# @app.post("/restart")
# def restart_bot(background_tasks: BackgroundTasks):
#     """Restart the mention-check loop and reset the last_mention_id"""
#     global running, last_mention_id
#     running = False
#     last_mention_id = None
#     running = True
#     background_tasks.add_task(check_mentions_periodically)
#     return {"status": "restarted", "last_mention_id": last_mention_id}

# @app.get("/debug/mentions")
# def debug_mentions():
#     mentions = twitter_client.get_mentions(since_id=last_mention_id)
#     return {"mentions_count": len(mentions), "mentions": [m.data for m in mentions]}

# @app.get("/debug/status")
# def debug_status():
#     return {"running": running, "last_mention_id": last_mention_id}
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)





from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import secrets
import logging
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import uvicorn
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
import asyncio
import json
import hashlib
import hmac
import base64
from urllib.parse import quote

# Load env
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", secrets.token_urlsafe(32))
LLM_API_URL = os.getenv("LLM_API_URL", "https://a8c4cosco0wc0gg8s40w8kco.vps.boomlive.in/query")

# Twitter API credentials
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# Twitter API URLs
TWITTER_API_BASE = "https://api.twitter.com/2"
TWITTER_API_V1_BASE = "https://api.twitter.com/1.1"

# Bot configuration
BOT_USERNAME = os.getenv("BOT_USERNAME", "").lower()
REPLY_TO_MENTIONS = os.getenv("REPLY_TO_MENTIONS", "true").lower() == "true"
REPLY_TO_DMS = os.getenv("REPLY_TO_DMS", "true").lower() == "true"
MAX_REPLY_LENGTH = int(os.getenv("MAX_REPLY_LENGTH", "280"))

# In-memory stores
processed_tweets: Dict[str, float] = {}
processed_dms: Dict[str, float] = {}
MESSAGE_EXPIRY = 3600  # 1 hour

# Rate limiting
rate_limits: Dict[str, List[float]] = {}
RATE_LIMIT_WINDOW = 900  # 15 minutes
RATE_LIMIT_REQUESTS = 300  # requests per window

# FastAPI setup
app = FastAPI(title="Twitter Chatbot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TwitterWebhookEvent(BaseModel):
    for_user_id: Optional[str] = None
    tweet_create_events: Optional[List[Dict[str, Any]]] = None
    direct_message_events: Optional[List[Dict[str, Any]]] = None
    users: Optional[Dict[str, Any]] = None

def cleanup_old_messages():
    """Remove expired message IDs and rate limit entries."""
    now = time.time()
    
    # Clean processed tweets
    expired_tweets = [tid for tid, ts in processed_tweets.items() if now - ts > MESSAGE_EXPIRY]
    for tid in expired_tweets:
        processed_tweets.pop(tid, None)
    
    # Clean processed DMs
    expired_dms = [dmid for dmid, ts in processed_dms.items() if now - ts > MESSAGE_EXPIRY]
    for dmid in expired_dms:
        processed_dms.pop(dmid, None)
    
    # Clean rate limits
    for key, timestamps in rate_limits.items():
        rate_limits[key] = [ts for ts in timestamps if now - ts < RATE_LIMIT_WINDOW]
    
    if expired_tweets or expired_dms:
        logger.info(f"Cleaned up {len(expired_tweets)} tweets, {len(expired_dms)} DMs")

def check_rate_limit(user_id: str) -> bool:
    """Check if user is within rate limits."""
    now = time.time()
    user_requests = rate_limits.get(user_id, [])
    
    # Remove old requests
    user_requests = [ts for ts in user_requests if now - ts < RATE_LIMIT_WINDOW]
    
    if len(user_requests) >= RATE_LIMIT_REQUESTS:
        return False
    
    # Add current request
    user_requests.append(now)
    rate_limits[user_id] = user_requests
    return True

def create_oauth_signature(method: str, url: str, params: Dict[str, str]) -> str:
    """Create OAuth 1.0a signature for Twitter API."""
    # OAuth parameters
    oauth_params = {
        'oauth_consumer_key': TWITTER_API_KEY,
        'oauth_token': TWITTER_ACCESS_TOKEN,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp': str(int(time.time())),
        'oauth_nonce': secrets.token_hex(16),
        'oauth_version': '1.0'
    }
    
    # Combine all parameters
    all_params = {**params, **oauth_params}
    
    # Create parameter string
    param_string = '&'.join([f"{quote(k)}={quote(str(v))}" for k, v in sorted(all_params.items())])
    
    # Create signature base string
    base_string = f"{method.upper()}&{quote(url)}&{quote(param_string)}"
    
    # Create signing key
    signing_key = f"{quote(TWITTER_API_SECRET)}&{quote(TWITTER_ACCESS_SECRET)}"
    
    # Create signature
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    
    oauth_params['oauth_signature'] = signature
    
    return oauth_params

def create_oauth_header(oauth_params: Dict[str, str]) -> str:
    """Create OAuth authorization header."""
    oauth_header = 'OAuth ' + ', '.join([f'{k}="{quote(str(v))}"' for k, v in sorted(oauth_params.items())])
    return oauth_header

async def get_twitter_client() -> httpx.AsyncClient:
    """Create HTTP client with proper authentication."""
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "Content-Type": "application/json"
    }
    return httpx.AsyncClient(headers=headers, timeout=30)

async def send_tweet_reply(tweet_id: str, reply_text: str, user_id: str) -> bool:
    """Send a reply to a tweet using Twitter API v2."""
    try:
        if not check_rate_limit(user_id):
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False
        
        # Truncate reply if too long
        if len(reply_text) > MAX_REPLY_LENGTH:
            reply_text = reply_text[:MAX_REPLY_LENGTH-3] + "..."
        
        url = f"{TWITTER_API_BASE}/tweets"
        
        # For API v2, we need OAuth 1.0a
        oauth_params = create_oauth_signature('POST', url, {})
        
        headers = {
            "Authorization": create_oauth_header(oauth_params),
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": reply_text,
            "reply": {
                "in_reply_to_tweet_id": tweet_id
            }
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if response.status_code == 201:
            logger.info(f"Successfully replied to tweet {tweet_id}")
            return True
        else:
            logger.error(f"Failed to reply to tweet: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending tweet reply: {e}")
        return False

async def send_direct_message(user_id: str, message_text: str) -> bool:
    """Send a direct message using Twitter API v1.1."""
    try:
        if not check_rate_limit(user_id):
            logger.warning(f"Rate limit exceeded for user {user_id}")
            return False
        
        # Truncate message if too long
        if len(message_text) > 10000:  # DM limit is 10,000 characters
            message_text = message_text[:9997] + "..."
        
        url = f"{TWITTER_API_V1_BASE}/direct_messages/events/new.json"
        
        oauth_params = create_oauth_signature('POST', url, {})
        
        headers = {
            "Authorization": create_oauth_header(oauth_params),
            "Content-Type": "application/json"
        }
        
        payload = {
            "event": {
                "type": "message_create",
                "message_create": {
                    "target": {
                        "recipient_id": user_id
                    },
                    "message_data": {
                        "text": message_text
                    }
                }
            }
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            logger.info(f"Successfully sent DM to user {user_id}")
            return True
        else:
            logger.error(f"Failed to send DM: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending direct message: {e}")
        return False

async def process_llm_request(text: str, user_id: str) -> str:
    """Process text through LLM API."""
    try:
        logger.info(f"LLM call for user {user_id}: {text[:50]}...")
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                LLM_API_URL, 
                params={
                    "question": text, 
                    "thread_id": f"twitter_{datetime.now().date().isoformat()}_{user_id}"
                }
            )
        
        if response.status_code == 200:
            return response.json().get("response", "No response available")
        else:
            logger.error(f"LLM API error {response.status_code}: {response.text}")
            return "Sorry, I'm having trouble processing your request right now."
            
    except Exception as e:
        logger.error(f"LLM request exception: {e}")
        return "Sorry, I encountered an error processing your request."

async def process_mention(tweet_data: Dict[str, Any], users: Dict[str, Any]):
    """Process a mention and reply to it."""
    tweet_id = tweet_data.get("id_str")
    tweet_text = tweet_data.get("text", "")
    author_id = tweet_data.get("user", {}).get("id_str")
    author_username = tweet_data.get("user", {}).get("screen_name", "")
    
    if not tweet_id or not author_id:
        return
    
    # Skip if already processed
    if tweet_id in processed_tweets:
        logger.info(f"Skipping duplicate tweet: {tweet_id}")
        return
    
    processed_tweets[tweet_id] = time.time()
    
    # Skip our own tweets
    if author_username.lower() == BOT_USERNAME:
        return
    
    # Remove @mentions from the text for processing
    words = tweet_text.split()
    clean_text = " ".join([word for word in words if not word.startswith("@")])
    
    if not clean_text.strip():
        clean_text = "Hello! How can I help you?"
    
    # Get LLM response
    llm_response = await process_llm_request(clean_text, author_id)
    
    # Add mention to reply
    reply_text = f"@{author_username} {llm_response}"
    
    # Send reply
    await send_tweet_reply(tweet_id, reply_text, author_id)

async def process_direct_message(dm_data: Dict[str, Any], users: Dict[str, Any]):
    """Process a direct message and respond."""
    dm_id = dm_data.get("id")
    message_data = dm_data.get("message_create", {})
    sender_id = message_data.get("sender_id")
    message_text = message_data.get("message_data", {}).get("text", "")
    
    if not dm_id or not sender_id or not message_text:
        return
    
    # Skip if already processed
    if dm_id in processed_dms:
        logger.info(f"Skipping duplicate DM: {dm_id}")
        return
    
    processed_dms[dm_id] = time.time()
    
    # Skip if it's from us (prevent loops)
    # You'll need to get your bot's user ID and store it
    BOT_USER_ID = os.getenv("BOT_USER_ID")
    if sender_id == BOT_USER_ID:
        return
    
    # Get LLM response
    llm_response = await process_llm_request(message_text, sender_id)
    
    # Send DM reply
    await send_direct_message(sender_id, llm_response)

def verify_webhook_signature(request_body: bytes, signature: str) -> bool:
    """Verify Twitter webhook signature."""
    if not WEBHOOK_SECRET:
        return True  # Skip verification if no secret is set
    
    try:
        # Twitter uses SHA-256 HMAC
        expected_signature = hmac.new(
            WEBHOOK_SECRET.encode(),
            request_body,
            hashlib.sha256
        ).digest()
        
        # Twitter sends signature as base64
        expected_signature_b64 = base64.b64encode(expected_signature).decode()
        
        # Remove 'sha256=' prefix if present
        if signature.startswith('sha256='):
            signature = signature[7:]
        
        return hmac.compare_digest(expected_signature_b64, signature)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

@app.get("/")
async def root():
    return {
        "message": "Twitter Chatbot API",
        "bot_username": BOT_USERNAME,
        "reply_to_mentions": REPLY_TO_MENTIONS,
        "reply_to_dms": REPLY_TO_DMS
    }

@app.get("/webhook")
async def webhook_challenge(request: Request):
    """Handle Twitter webhook challenge (CRC)."""
    crc_token = request.query_params.get("crc_token")
    if not crc_token:
        return Response(status_code=400)
    
    # Create challenge response
    challenge_response = hmac.new(
        WEBHOOK_SECRET.encode(),
        crc_token.encode(),
        hashlib.sha256
    ).digest()
    
    return {
        "response_token": "sha256=" + base64.b64encode(challenge_response).decode()
    }

@app.post("/webhook")
async def webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """Handle Twitter webhook events."""
    try:
        # Get request body and signature
        body = await request.body()
        signature = request.headers.get("x-twitter-webhooks-signature", "")
        
        # Verify signature
        if not verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            return Response(status_code=401)
        
        # Parse JSON
        try:
            data = json.loads(body.decode())
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook")
            return Response(status_code=400)
        
        # Clean up old messages periodically
        cleanup_old_messages()
        
        # Process tweet mentions
        if REPLY_TO_MENTIONS and data.get("tweet_create_events"):
            for tweet in data["tweet_create_events"]:
                # Check if it's a mention
                entities = tweet.get("entities", {})
                user_mentions = entities.get("user_mentions", [])
                
                is_mention = any(
                    mention.get("screen_name", "").lower() == BOT_USERNAME 
                    for mention in user_mentions
                )
                
                if is_mention:
                    background_tasks.add_task(
                        process_mention, 
                        tweet, 
                        data.get("users", {})
                    )
        
        # Process direct messages
        if REPLY_TO_DMS and data.get("direct_message_events"):
            for dm in data["direct_message_events"]:
                background_tasks.add_task(
                    process_direct_message, 
                    dm, 
                    data.get("users", {})
                )
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Webhook handler error: {e}")
        return Response(status_code=500)

@app.get("/status")
async def status():
    """Get bot status and statistics."""
    return {
        "processed_tweets": len(processed_tweets),
        "processed_dms": len(processed_dms),
        "active_rate_limits": len([k for k, v in rate_limits.items() if v]),
        "server_time": datetime.now().isoformat(),
        "config": {
            "bot_username": BOT_USERNAME,
            "reply_to_mentions": REPLY_TO_MENTIONS,
            "reply_to_dms": REPLY_TO_DMS,
            "max_reply_length": MAX_REPLY_LENGTH
        }
    }

@app.post("/send-tweet")
async def send_tweet(request: Request):
    """Manually send a tweet (for testing)."""
    try:
        data = await request.json()
        text = data.get("text", "")
        
        if not text:
            return {"error": "Text is required"}
        
        url = f"{TWITTER_API_BASE}/tweets"
        oauth_params = create_oauth_signature('POST', url, {})
        
        headers = {
            "Authorization": create_oauth_header(oauth_params),
            "Content-Type": "application/json"
        }
        
        payload = {"text": text}
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=payload)
        
        if response.status_code == 201:
            return {"success": True, "tweet": response.json()}
        else:
            return {"error": f"Failed to send tweet: {response.text}"}
            
    except Exception as e:
        logger.error(f"Send tweet error: {e}")
        return {"error": str(e)}

@app.get("/test-llm")
async def test_llm(question: str = "Hello, how are you?"):
    """Test LLM API connection."""
    response = await process_llm_request(question, "test_user")
    return {"question": question, "response": response}

# Background cleanup task
async def cleanup_background_task():
    """Background task to clean up old data periodically."""
    while True:
        try:
            await asyncio.sleep(1800)  # 30 minutes
            cleanup_old_messages()
        except Exception as e:
            logger.error(f"Background cleanup error: {e}")

@app.on_event("startup")
async def startup_event():
    """Initialize the bot on startup."""
    logger.info("Starting Twitter Chatbot...")
    
    # Validate required credentials
    required_creds = [
        TWITTER_API_KEY, TWITTER_API_SECRET, 
        TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET, 
        TWITTER_BEARER_TOKEN
    ]
    
    if not all(required_creds):
        logger.error("Missing required Twitter API credentials!")
        return
    
    if not BOT_USERNAME:
        logger.warning("BOT_USERNAME not set - mention detection may not work properly")
    
    # Start background cleanup
    asyncio.create_task(cleanup_background_task())
    
    logger.info(f"Twitter Chatbot initialized successfully")
    logger.info(f"Bot: @{BOT_USERNAME}")
    logger.info(f"Mentions: {'Enabled' if REPLY_TO_MENTIONS else 'Disabled'}")
    logger.info(f"DMs: {'Enabled' if REPLY_TO_DMS else 'Disabled'}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)), 
        reload=True
    )