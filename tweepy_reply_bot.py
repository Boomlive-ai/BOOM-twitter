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
env_loaded = load_dotenv()

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
LLM_API_URL                 = os.getenv("LLM_API_URL")
DEFAULT_REPLY               = "Sorry, I can't answer right now."

# FREE TIER ULTRA-CONSERVATIVE SETTINGS
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))  # 1 hour default
MAX_REQUESTS_PER_HOUR = 3  # Very conservative for free tier
MIN_REQUEST_INTERVAL = 1200  # 20 minutes between requests

# Rate limiting tracking
request_times = []
last_mention_id = None
last_dm_id = None
daily_requests = 0
last_reset_date = datetime.now().date()

# Validate credentials
required = [TWITTER_API_KEY, TWITTER_API_SECRET,
            TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]
if not all(required):
    logger.error("Missing Twitter API credentials in .env")
    raise SystemExit(1)

if not BOT_USERNAME:
    logger.warning("BOT_USERNAME not set; mention polling may not detect your bot correctly.")

# Tweepy client with rate limit handling
client = tweepy.Client(
    bearer_token=TWITTER_BEARER_TOKEN,
    consumer_key=TWITTER_API_KEY,
    consumer_secret=TWITTER_API_SECRET,
    access_token=TWITTER_ACCESS_TOKEN,
    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    wait_on_rate_limit=True
)

def can_make_request():
    """Check if we can make a request based on rate limits"""
    global request_times, daily_requests, last_reset_date
    
    current_time = time.time()
    current_date = datetime.now().date()
    
    # Reset daily counter if new day
    if current_date > last_reset_date:
        daily_requests = 0
        last_reset_date = current_date
        logger.info("Daily request counter reset")
    
    # Remove requests older than 1 hour
    one_hour_ago = current_time - 3600
    request_times = [t for t in request_times if t > one_hour_ago]
    
    # Check hourly limit
    if len(request_times) >= MAX_REQUESTS_PER_HOUR:
        logger.warning(f"Hourly limit reached ({MAX_REQUESTS_PER_HOUR} requests)")
        return False
    
    # Check minimum interval since last request
    if request_times and (current_time - request_times[-1]) < MIN_REQUEST_INTERVAL:
        logger.info("Minimum interval not met, skipping request")
        return False
    
    # Check if we have any requests left for today (very conservative estimate)
    if daily_requests >= 20:  # Ultra-conservative daily limit for free tier
        logger.warning("Daily request limit reached")
        return False
    
    return True

def record_request():
    """Record that we made a request"""
    global request_times, daily_requests
    request_times.append(time.time())
    daily_requests += 1

async def fetch_llm_response(question: str, thread_id: str) -> str:
    """Fetch response from LLM API with timeout"""
    try:
        resp = requests.get(
            LLM_API_URL, 
            params={"question": question, "thread_id": thread_id}, 
            timeout=10
        )
        if resp.status_code == 200:
            return resp.text.strip()
        else:
            logger.warning(f"LLM API returned status {resp.status_code}")
    except requests.exceptions.Timeout:
        logger.error("LLM API request timed out")
    except Exception as e:
        logger.error(f"LLM request failed: {e}")
    return DEFAULT_REPLY

async def poll_mentions():
    """Poll for mentions with aggressive rate limiting"""
    global last_mention_id
    
    query = f"@{BOT_USERNAME} -is:retweet"
    consecutive_errors = 0
    
    while True:
        try:
            # Check if we can make a request
            if not can_make_request():
                logger.info("Rate limit check failed, waiting...")
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            
            logger.info("Checking for new mentions...")
            
            # Make the API request (simplified for free tier)
            params = {
                "query": query,
                "max_results": 5  # Reduced to minimum
            }
            
            if last_mention_id:
                params["since_id"] = last_mention_id
            
            response = client.search_recent_tweets(**params)
            record_request()
            
            if response.data:
                tweets = list(reversed(response.data))  # Process oldest first
                logger.info(f"Found {len(tweets)} new mentions")
                
                for tweet in tweets:
                    try:
                        # Update last_mention_id
                        if not last_mention_id or int(tweet.id) > int(last_mention_id):
                            last_mention_id = tweet.id
                        
                        # Skip age check since we don't have created_at in free tier
                        # Free tier doesn't provide tweet.fields
                        
                        # Process the mention (simplified for free tier)
                        await process_mention(tweet)
                        
                        # Small delay between processing tweets
                        await asyncio.sleep(5)
                        
                    except Exception as e:
                        logger.error(f"Error processing tweet {tweet.id}: {e}")
                        continue
            else:
                logger.info("No new mentions found")
            
            consecutive_errors = 0
            
        except tweepy.TooManyRequests as e:
            logger.warning("Rate limit exceeded")
            # Extract reset time from response headers
            reset_time = 900  # Default 15 minutes
            if hasattr(e, 'response') and e.response:
                reset_header = e.response.headers.get('x-rate-limit-reset')
                if reset_header:
                    try:
                        reset_timestamp = int(reset_header)
                        reset_time = max(reset_timestamp - int(time.time()), 60)
                    except:
                        pass
            
            logger.info(f"Sleeping for {reset_time} seconds until rate limit resets")
            await asyncio.sleep(reset_time)
            continue
            
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Error in poll_mentions (attempt {consecutive_errors}): {e}")
            
            if consecutive_errors >= 5:
                logger.error("Too many consecutive errors, sleeping longer")
                await asyncio.sleep(CHECK_INTERVAL * 2)
                consecutive_errors = 0
            else:
                await asyncio.sleep(60)  # Short delay before retry
            continue
        
        # Wait before next check
        logger.info(f"Waiting {CHECK_INTERVAL} seconds before next check")
        await asyncio.sleep(CHECK_INTERVAL)

async def process_mention(tweet):
    """Process a single mention (simplified for free tier)"""
    try:
        # For free tier, we can't get username easily, so use generic greeting
        author_username = "friend"  # Generic since we can't get user details
        
        # Extract question from tweet
        tweet_text = tweet.text
        question = tweet_text.replace(f"@{BOT_USERNAME}", "").strip()
        if not question:
            question = "Hello!"
        
        logger.info(f"Processing mention: {question[:50]}...")
        
        # Get LLM response
        response = await fetch_llm_response(question, f"twitter_{tweet.author_id}")
        
        # Truncate response if too long
        if len(response) > 250:  # Leave room for username
            response = response[:247] + "..."
        
        # Check if we can make another request to reply
        if not can_make_request():
            logger.warning("Cannot reply due to rate limits")
            return
        
        # Reply to the tweet (without username since we can't get it in free tier)
        reply_text = f"Hi! {response}"
        client.create_tweet(
            text=reply_text,
            in_reply_to_tweet_id=tweet.id
        )
        record_request()
        
        logger.info(f"Replied to tweet {tweet.id}")
        
    except Exception as e:
        logger.error(f"Failed to process mention: {e}")

# Simplified DM polling (optional)
async def poll_dms():
    """Poll for DMs with heavy rate limiting"""
    global last_dm_id
    
    # Create API v1.1 client for DMs
    auth = tweepy.OAuth1UserHandler(
        TWITTER_API_KEY, TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
    )
    api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
    
    while True:
        try:
            if not can_make_request():
                await asyncio.sleep(CHECK_INTERVAL * 2)  # Wait longer for DMs
                continue
            
            logger.info("Checking for new DMs...")
            dms = api_v1.get_direct_messages(count=10)
            record_request()
            
            new_dms = []
            for dm in reversed(dms):
                if last_dm_id and int(dm.id) <= int(last_dm_id):
                    continue
                new_dms.append(dm)
                last_dm_id = dm.id
            
            if new_dms:
                logger.info(f"Found {len(new_dms)} new DMs")
                for dm in new_dms:
                    await process_dm(dm, api_v1)
                    await asyncio.sleep(10)  # Longer delay between DM processing
            else:
                logger.info("No new DMs found")
                
        except Exception as e:
            logger.error(f"Error in poll_dms: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL * 2)  # Check DMs less frequently

async def process_dm(dm, api_v1):
    """Process a single DM"""
    try:
        sender_id = dm.message_create['sender_id']
        message_text = dm.message_create['message_data']['text']
        
        question = message_text.strip() or "Hello!"
        logger.info(f"Processing DM: {question[:50]}...")
        
        response = await fetch_llm_response(question, f"dm_{sender_id}")
        
        if not can_make_request():
            logger.warning("Cannot reply to DM due to rate limits")
            return
        
        api_v1.send_direct_message(recipient_id=sender_id, text=response)
        record_request()
        logger.info(f"Replied to DM from {sender_id}")
        
    except Exception as e:
        logger.error(f"Failed to process DM: {e}")

# FastAPI app
app = FastAPI(title="Free Tier Twitter Bot")

# Environment settings
REPLY_TO_DMS = os.getenv("REPLY_TO_DMS", "false").lower() == "true"

@app.on_event("startup")
async def startup():
    logger.info("Starting Free Tier Twitter Bot...")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
    logger.info(f"Max requests per hour: {MAX_REQUESTS_PER_HOUR}")
    logger.info(f"Min request interval: {MIN_REQUEST_INTERVAL} seconds")
    
    # Start mention polling
    asyncio.create_task(poll_mentions())
    
    # Start DM polling if enabled
    if REPLY_TO_DMS:
        logger.info("DM polling enabled")
        asyncio.create_task(poll_dms())
    else:
        logger.info("DM polling disabled")

@app.get("/")
def root():
    return {
        "status": "running",
        "mode": "free_tier_polling",
        "last_mention_id": last_mention_id,
        "last_dm_id": last_dm_id,
        "daily_requests": daily_requests,
        "hourly_requests": len(request_times),
        "next_check_in": f"{CHECK_INTERVAL} seconds"
    }

@app.get("/stats")
def stats():
    return {
        "daily_requests": daily_requests,
        "hourly_requests": len(request_times),
        "last_reset_date": str(last_reset_date),
        "rate_limits": {
            "max_per_hour": MAX_REQUESTS_PER_HOUR,
            "min_interval": MIN_REQUEST_INTERVAL,
            "check_interval": CHECK_INTERVAL
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)