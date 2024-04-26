# Welcome to the Summarizer!

This project summarizes the [bitcoin-dev](https://gnusha.org/pi/bitcoindev), [lightning-dev](https://lists.linuxfoundation.org/pipermail/lightning-dev) mailing lists, and [Delving Bitcoin](https://delvingbitcoin.org/) website.

## Overview

Utilizing data collected by the [scraper](https://github.com/bitcoinsearch/scraper) and stored in an Elasticsearch index, it uses several nightly cron jobs to automate the generation of easily accessible summarization feeds for public consumption.

### Current cron jobs

1. Daily [XML Generation](.github/workflows/xmls_gen_cron_job.yml) ([source](xmls_generator_production.py))
   - Queries Elasticsearch for documents from the last 30 days across each source. For each source, it retrieves existing XML files/summaries, while generating summaries for new posts (those lacking XML file).
   For each thread, it compiles inputs to generate a combined thread summary. This compilation includes the summaries of previous posts and the actual content of newer posts that have been added since the last run. 
   All generated summaries, both individual and combined, are formatted into XML files and committed to GitHub to be used by [Bitcoin TLDR](https://github.com/bitcoinsearch/tldr).
2. Daily [Push Summary From XML Files to ES INDEX](.github/workflows/push_summary_to_elasticsearch_cron_job.yml) ([source](push_summary_to_es.py))
   - Queries Elasticsearch for documents lacking summaries, extracts summaries from corresponding XML files, and then updates these documents with their summaries in the Elasticsearch index.
3. Daily [Push Combined Summary From XML Files to ES INDEX](.github/workflows/push_combined_summary_to_es_cron_job.yml) ([source](push_combined_summary_to_es.py))
   - Processes each combined thread summary XML file, transforming it into a document format, checks for its existence in Elasticsearch, and updates or inserts the document as needed.
4. Daily [Python Homepage Update Script](.github/workflows/homepage_json_gen_cron_job.yml) ([source](generate_homepage_xml.py))
   - Queries the last 7 days of data from Elasticsearch for each source to compile lists of active threads, recent threads, and historical threads for 'Today in History'. It generates a summary of recent threads if available; otherwise, for active threads. The resulting [`homepage.json`](static/homepage.json) is then committed to GitHub to be used by [Bitcoin TLDR](https://github.com/bitcoinsearch/tldr).
5. Weekly [Python Newsletter Generation Script](.github/workflows/weekly_newsletter_gen_cron_job.yml) ([source](generate_weekly_newsletter_json.py))
   - Generates a newsletter by compiling lists of new and active threads from the past week's data for each source. It generates a summary of new threads if available; otherwise, for active threads. The resulting [`newsletter.json`](static/newsletters/newsletter.json) is then committed to GitHub to be used by [Bitcoin TLDR](https://github.com/bitcoinsearch/tldr).


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
