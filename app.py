import os
import openai
from dotenv import load_dotenv
from flask import Flask, request
from src import utils

import warnings
warnings.filterwarnings("ignore")

load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "<h1>Hello, World!</h1>"


@app.route("/generate-newsletter", methods=['GET', 'POST'])
def generate_newsletter():
    data = request.json
    mailing_list_base_url = data['mailing_list_url']
    # eg., https://lists.linuxfoundation.org/pipermail/bitcoin-dev
    all_email_urls = utils.collect_email_urls(mailing_list_base_url)
    df_week = utils.scrape_email_urls(all_email_urls)
    df_week_generated = utils.generate_newsletter_completion(df_week)
    save_file_name = f"html_newsletter_{utils.CURRENT_TIMESTAMP}.html"
    html_file_path = utils.save_html_file(df_week_generated, save_file_name)
    return html_file_path


if __name__ == '__main__':
    app.run(debug=True)
