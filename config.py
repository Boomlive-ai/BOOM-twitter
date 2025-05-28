import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Twitter API Credentials
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")

# Query API URL
QUERY_API_URL = os.getenv("QUERY_API_URL")

# Check interval in seconds
CHECK_INTERVAL = 30  # Changed from 5 to 30 seconds to reduce API usage

# Default thread ID for the query API
DEFAULT_THREAD_ID = "default"