# Goal

Summarize the [bitcoin-dev](https://lists.linuxfoundation.org/pipermail/bitcoin-dev) and [lightning-dev](https://lists.linuxfoundation.org/pipermail/lightning-dev) mailing lists with the goal of creating a feed for public consumption. This project scrapes the mailing lists and then creates summaries based on date.

### Project Setup
1. Install all the dependencies from requirements.txt file: `pip install -r requirements.txt`
2. Set up environment variables: Create `.env` file in the root folder and add following keys -
    ```
   OPENAI_API_KEY="<your_api-Key>"
   ES_CLOUD_ID = "<your_es_cloud_id>"
   ES_USERNAME = "<your_es_username>"
   ES_PASSWORD = "<your_es_password>"
   ES_INDEX = ""<your_es_index>""
   ```
3. In `src > config.py` file, set `CHATGPT=True` if you want to generate results using chatgpt model, else set it to `False` and assign `COMPLETION_MODEL` variable with the model's name.
4. Run an app using command: `python app.py`
5. Directories: 
   * `postman_collection`: APIs
   * `output`: generate results on api call
   * `notebook`: jupyter-notebook with all the scripts
