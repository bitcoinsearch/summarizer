import tiktoken
import os
from dotenv import load_dotenv
load_dotenv()

TOKENIZER = tiktoken.get_encoding("cl100k_base")

# if set to True, it will use chatgpt model ("gpt-4-1106-preview") for all the completions
CHATGPT = True

# COMPLETION_MODEL - only applicable if CHATGPT is set to False
COMPLETION_MODEL = "text-davinci-003"  # "text-ada-001",
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ES_CLOUD_ID= os.getenv("ES_CLOUD_ID")
ES_USERNAME = os.getenv("ES_USERNAME")
ES_PASSWORD = os.getenv("ES_PASSWORD")
ES_INDEX = os.getenv("ES_INDEX")
ES_DATA_FETCH_SIZE = 10000  # No. of data to fetch and save from elastic-search
