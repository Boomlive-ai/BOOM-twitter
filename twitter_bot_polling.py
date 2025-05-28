import os
import time
import logging
import asyncio
from fastapi import FastAPI
from dotenv import load_dotenv
import tweepy
import requests
from datetime import datetime, timedelta

# Load env
load_dotenv()

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
CHECK_INTERVAL              = 660  # 15 minutes = 900 seconds
LLM_API_URL                 = os.getenv("LLM_API_URL")
DEFAULT_REPLY               = "Sorry, I can't answer right now."

# Free tier limits (adjust as needed for testing)
MAX_TWEETS_PER_POLL = 20  # Reduced for free tier
DELAY_BETWEEN_REPLIES = 5  # Seconds between replies to avoid rate limits

# Validate credentials
required = [TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]
if not all(required):
    logger.error("Missing Twitter API credentials in .env")
    raise SystemExit(1)
if not BOT_USERNAME:
    logger.error("BOT_USERNAME is required for mention detection")
    raise SystemExit(1)
if not LLM_API_URL:
    logger.warning("LLM_API_URL not set; will use default replies.")

# Tweepy client - Free tier setup
client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=False  # We'll handle rate limits manually for better control
)

# Track last processed IDs and startup time
last_mention_id = None
bot_start_time = datetime.utcnow()
processed_tweet_ids = set()  # Keep track of processed tweets to avoid duplicates

async def fetch_llm_response(question: str, thread_id: str) -> str:
    """Fetch response from LLM API with error handling"""
    if not LLM_API_URL:
        return DEFAULT_REPLY
    
    try:
        logger.info(f"Sending to LLM: {question[:50]}...")
        resp = requests.get(
            LLM_API_URL, 
            params={"question": question, "thread_id": thread_id}, 
            timeout=30
        )
        if resp.status_code == 200:
            response_json = resp.json()  # Convert response to a dictionary
            response_text = response_json.get("response", DEFAULT_REPLY)  # Extract the actual response
            print(response_text)
            logger.info(f"LLM response received: {len(response_text)} characters")
            return response_text
        else:
            logger.error(f"LLM API returned status {resp.status_code}")
    except requests.exceptions.Timeout:
        logger.error("LLM request timed out")
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
    
    return DEFAULT_REPLY

async def get_user_info(user_id: str) -> dict:
    """Get user information from user ID with caching"""
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
    """Poll for mentions every 15 minutes - Free tier optimized"""
    global last_mention_id
    
    logger.info(f"🚀 Starting mention polling (every {CHECK_INTERVAL/60} minutes)")
    logger.info(f"Bot username: @{BOT_USERNAME}")
    
    # Wait before first poll
    logger.info("Waiting 30 seconds before first mention poll...")
    await asyncio.sleep(30)
    
    # Search query - optimized for free tier
    query = f"@{BOT_USERNAME} -is:retweet"

    poll_count = 0
    
    while True:
        poll_count += 1
        try:
            logger.info(f"🔍 Poll #{poll_count}: Checking for new mentions...")
            
            # Build search parameters for free tier
            params = {
                "query": query,
                "max_results": MAX_TWEETS_PER_POLL,
                "tweet_fields": ["author_id", "created_at", "public_metrics"],
                "user_fields": ["username"]
            }

            # Use since_id only if we have processed tweets before
            if last_mention_id:
                params["since_id"] = last_mention_id
            
            try:
                resp = client.search_recent_tweets(**params)
                tweets = resp.data if resp.data else []
                users = {user.id: user for user in (resp.includes.get('users', []) if resp.includes else [])}
                print(f"USERS: {users}")
            except tweepy.TooManyRequests as e:
                wait_time = int(e.response.headers.get("x-rate-limit-reset", time.time())) - time.time()
                print(f"Wait time: {wait_time}")
                wait_time = max(wait_time, 60)  # Ensure a minimum wait of 1 minute
                logger.warning(f"⚠️ Rate limit hit, sleeping for {wait_time//60} minutes...")
                await asyncio.sleep(wait_time)
                continue
            except tweepy.Unauthorized:
                logger.error("❌ Authentication failed - check your credentials")
                await asyncio.sleep(300)
                continue
            except Exception as e:
                logger.error(f"❌ Error searching tweets: {e}")
                await asyncio.sleep(60)
                continue

            if not tweets:
                logger.info("✅ No new mentions found")
            else:
                logger.info(f"📧 Found {len(tweets)} new mentions")
                
                # Process tweets in chronological order (oldest first)
                successful_replies = 0
                for tweet in reversed(tweets):
                    try:
                        # Skip if already processed
                        if tweet.id in processed_tweet_ids:
                            logger.info(f"⏭️ Skipping already processed tweet {tweet.id}")
                            continue
                        
                        # Update tracking
                        last_mention_id = max(int(last_mention_id or 0), tweet.id)
                        processed_tweet_ids.add(tweet.id)
                        
                        # Skip old tweets (from before bot started)
                        if tweet.created_at:
                            tweet_time = tweet.created_at.replace(tzinfo=None)
                            if tweet_time < bot_start_time:
                                logger.info(f"⏭️ Skipping old tweet {tweet.id}")
                                continue
                        
                        # Extract question text
                        text = tweet.text.replace(f"@{BOT_USERNAME}", "").strip()
                        if not text:
                            text = "Hello!"
                        
                        logger.info(f"📝 Processing tweet {tweet.id}: {text[:50]}...")
                        
                        # Get user info
                        user_info = await get_user_info(str(tweet.author_id))
                        username = user_info["username"]
                        
                        # Get LLM response
                        reply = await fetch_llm_response(text, str(tweet.author_id))
                        
                        # Ensure reply fits Twitter's character limit
                        max_reply_length = 250  # Leave room for @username
                        if len(reply) > max_reply_length:
                            reply = reply[:max_reply_length-3] + "..."
                        
                        # Create reply text
                        reply_text = f"@{username} {reply}"
                        
                        # Post reply
                        try:
                            response_tweet = client.create_tweet(
                                text=reply_text,
                                in_reply_to_tweet_id=tweet.id
                            )
                            print(f"Reply created: {response_tweet.data.id}")
                            logger.info(f"✅ Successfully replied to @{username} (tweet {tweet.id})")
                            successful_replies += 1
                            
                            # Delay between replies to avoid rate limits
                            if DELAY_BETWEEN_REPLIES > 0:
                                await asyncio.sleep(DELAY_BETWEEN_REPLIES)
                                
                        except tweepy.TooManyRequests:
                            logger.warning("⚠️ Rate limit hit on tweet creation, skipping remaining tweets")
                            break
                        except tweepy.Forbidden as e:
                            logger.error(f"🚫 Forbidden to reply to tweet {tweet.id}: {e}")
                            continue
                        except Exception as e:
                            logger.error(f"❌ Error creating reply for tweet {tweet.id}: {e}")
                            continue
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing tweet {tweet.id}: {e}")
                        continue
                
                logger.info(f"📊 Successfully replied to {successful_replies}/{len(tweets)} mentions")

        except Exception as e:
            logger.error(f"❌ Unexpected error in polling loop: {e}")
            await asyncio.sleep(60)
        
        # Clean up processed_tweet_ids periodically to prevent memory growth
        if len(processed_tweet_ids) > 1000:
            processed_tweet_ids.clear()
            logger.info("🧹 Cleared processed tweet IDs cache")
        
        # Wait for next poll cycle
        next_poll_time = datetime.utcnow() + timedelta(seconds=CHECK_INTERVAL)
        logger.info(f"💤 Sleeping until next poll at {next_poll_time.strftime('%H:%M:%S')} ({CHECK_INTERVAL/60} minutes)")
        await asyncio.sleep(CHECK_INTERVAL)

# FastAPI app
app = FastAPI(title="Twitter Bot - Free Tier", version="1.0.0")

@app.on_event("startup")
async def startup():
    """Start the polling tasks"""
    logger.info("🚀 Starting Twitter bot (Free Tier Version)")
    logger.info(f"Bot username: @{BOT_USERNAME}")
    logger.info(f"Check interval: {CHECK_INTERVAL/60} minutes")
    logger.info(f"Max tweets per poll: {MAX_TWEETS_PER_POLL}")
    logger.info(f"LLM API URL: {LLM_API_URL}")
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
    """Health check endpoint"""
    return {
        "status": "running",
        "version": "free_tier",
        "bot_username": BOT_USERNAME,
        "check_interval_minutes": CHECK_INTERVAL / 60,
        "max_tweets_per_poll": MAX_TWEETS_PER_POLL,
        "last_mention_id": last_mention_id,
        "processed_tweets_count": len(processed_tweet_ids),
        "started_at": bot_start_time.isoformat(),
        "features": {
            "mention_replies": True,
            "dm_replies": False,
            "rate_limit_handling": True
        }
    }

@app.get("/health")
def health():
    """Detailed health check"""
    uptime = datetime.utcnow() - bot_start_time
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": uptime.total_seconds(),
        "uptime_human": str(uptime),
        "last_mention_id": last_mention_id,
        "api_limits": {
            "tier": "free",
            "max_tweets_per_poll": MAX_TWEETS_PER_POLL,
            "delay_between_replies": DELAY_BETWEEN_REPLIES
        }
    }

@app.get("/stats")
def stats():
    """Bot statistics"""
    return {
        "processed_tweets": len(processed_tweet_ids),
        "last_mention_id": last_mention_id,
        "bot_start_time": bot_start_time.isoformat(),
        "next_poll_in_seconds": CHECK_INTERVAL,
        "configuration": {
            "bot_username": BOT_USERNAME,
            "check_interval_minutes": CHECK_INTERVAL / 60,
            "llm_api_configured": bool(LLM_API_URL)
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server...")
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)), 
        log_level="info"
    )