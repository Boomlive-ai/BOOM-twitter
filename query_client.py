import requests
import logging
import time
from config import QUERY_API_URL, DEFAULT_THREAD_ID

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QueryClient:
    def __init__(self, api_url=QUERY_API_URL):
        self.api_url = api_url
        logger.info(f"Initialized QueryClient with API URL: {api_url}")
    
    def get_response(self, question, thread_id=DEFAULT_THREAD_ID, max_retries=3, retry_delay=2):
        """
        Get a response from the query API for a given question
        
        Args:
            question (str): The question to send to the API
            thread_id (str): The thread ID to use (default is 'default')
            max_retries (int): Maximum number of retry attempts
            retry_delay (int): Delay between retries in seconds
            
        Returns:
            str: The response from the API or None if there was an error
        """
        attempts = 0
        while attempts < max_retries:
            try:
                # Prepare the query parameters
                params = {
                    "question": question,
                    "thread_id": thread_id
                }
                
                logger.info(f"Sending question to API: '{question}' with thread_id '{thread_id}' (Attempt {attempts+1}/{max_retries})")
                
                # Make the API request
                response = requests.get(self.api_url, params=params, timeout=10)  # Adding a timeout
                
                # Check if the request was successful
                if response.status_code == 200:
                    response_text = response.text
                    logger.info(f"Received response from API: '{response_text[:100]}...'")
                    return response_text
                else:
                    logger.error(f"API request failed with status code {response.status_code}: {response.text}")
                    # If we get a 5xx error, retry. Otherwise, fail immediately
                    if 500 <= response.status_code < 600:
                        attempts += 1
                        if attempts < max_retries:
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            continue
                    return None
                    
            except requests.Timeout:
                logger.error("API request timed out")
                attempts += 1
                if attempts < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    return None
            except Exception as e:
                logger.error(f"Error making API request: {str(e)}")
                attempts += 1
                if attempts < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    return None