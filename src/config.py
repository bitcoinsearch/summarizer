import os
import openai
import warnings

import tiktoken
from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings("ignore")

OPENAI_ORG_KEY = os.getenv("OPENAI_ORG_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.organization = OPENAI_ORG_KEY
openai.api_key = OPENAI_API_KEY

TOKENIZER = tiktoken.get_encoding("cl100k_base")

# if set to True, it will use chatgpt model ("gpt-4-1106-preview") for all the completions
CHATGPT = True
# COMPLETION_MODEL is for chatgpt
COMPLETION_MODEL = "text-davinci-003"  # "text-ada-001"

# used in generation of xmls production, homepage, newsletter etc.
CHAT_COMPLETION_MODEL = "gpt-4-turbo-preview"  # "gpt-3.5-turbo", "gpt-4"

ES_CLOUD_ID = os.getenv("ES_CLOUD_ID")
ES_USERNAME = os.getenv("ES_USERNAME")
ES_PASSWORD = os.getenv("ES_PASSWORD")
ES_INDEX = os.getenv("ES_INDEX")
ES_DATA_FETCH_SIZE = 10000  # No. of data to fetch and save from elastic-search
