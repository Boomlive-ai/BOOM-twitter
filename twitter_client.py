import tweepy
import logging
import time
from config import (
    TWITTER_API_KEY, TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET,
    TWITTER_BEARER_TOKEN, TWITTER_USERNAME
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TwitterClient:
    def __init__(self):
        """Initialize the Twitter client with the provided credentials"""
        try:
            # Initialize Twitter API v2 client
            self.client = tweepy.Client(
                bearer_token=TWITTER_BEARER_TOKEN,
                consumer_key=TWITTER_API_KEY,
                consumer_secret=TWITTER_API_SECRET,
                access_token=TWITTER_ACCESS_TOKEN,
                access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
            )
            
            # Store username for reference
            self.username = TWITTER_USERNAME
            
            # Get the authenticated user's ID
            self.user_id = self._get_user_id()
            
            logger.info(f"TwitterClient initialized for user @{TWITTER_USERNAME} (ID: {self.user_id})")
        
        except Exception as e:
            logger.error(f"Error initializing Twitter client: {str(e)}")
            raise
    
    def _get_user_id(self):
        """Get the authenticated user's ID"""
        try:
            user = self.client.get_user(username=TWITTER_USERNAME)
            return user.data.id
        except Exception as e:
            logger.error(f"Failed to get user ID for @{TWITTER_USERNAME}: {str(e)}")
            raise
    
    def get_mentions(self, since_id=None):
        """
        Get tweets mentioning the authenticated user
        
        Args:
            since_id (str, optional): Only return mentions newer than this ID
            
        Returns:
            list: List of mentions
        """
        try:
            # Use Twitter API v2 to search for recent mentions
            query = f"@{TWITTER_USERNAME} -is:retweet"
            
            # Set up parameters for the search
            params = {
                "query": query,
                "max_results": 5  # Reduced from 10 to 5 to stay well within rate limits
            }
            
            # Add since_id if provided
            if since_id:
                params["since_id"] = since_id
                
            # Search for tweets
            response = self.client.search_recent_tweets(**params)
            
            if response.data:
                mentions = response.data
                logger.info(f"Found {len(mentions)} new mentions")
                return mentions
            else:
                logger.info("No new mentions found")
                return []
                
        except tweepy.TooManyRequests as e:
            logger.error(f"Rate limit exceeded: {str(e)}")
            # You might want to extract the 'reset' time from the error and adjust your sleep time
            return []
        except tweepy.TwitterServerError as e:
            logger.error(f"Twitter server error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting mentions: {str(e)}")
            return []
    
    def reply_to_tweet(self, tweet_id, text):
        """
        Reply to a specific tweet
        
        Args:
            tweet_id (str): ID of the tweet to reply to
            text (str): Text of the reply
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Reply to the tweet
            response = self.client.create_tweet(
                text=text,
                in_reply_to_tweet_id=tweet_id
            )
            
            if response.data:
                reply_id = response.data["id"]
                logger.info(f"Successfully replied to tweet {tweet_id} with tweet {reply_id}")
                return True
            else:
                logger.error(f"Failed to reply to tweet {tweet_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error replying to tweet {tweet_id}: {str(e)}")
            return False
    
    def filter_bot_tweets(self, mentions):
        """
        Filter out mentions from known bots or to avoid reply loops
        
        Args:
            mentions (list): List of tweet mentions
            
        Returns:
            list: Filtered list of mentions
        """
        # This is a simple implementation. You may want to expand on this
        # to identify bot accounts or detect reply loops
        filtered_mentions = []
        
        for mention in mentions:
            # Skip self-mentions
            if str(mention.author_id) == str(self.user_id):
                continue
            
            # Add more filtering logic here as needed
            
            filtered_mentions.append(mention)
        
        return filtered_mentions