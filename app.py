import os
import openai
from dotenv import load_dotenv
from flask import Flask, request, Response, render_template, url_for
from src import utils
from feedgen.feed import FeedGenerator
import feedparser
import warnings

warnings.filterwarnings("ignore")

load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")

app = Flask(__name__)


def get_xml_files(year_month):
    year_month_dir = os.path.join(os.path.join(app.root_path, 'static'), year_month)
    xml_files = [f for f in os.listdir(year_month_dir) if f.endswith('.xml')]
    return xml_files


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


@app.route('/<year_month>')
def feed(year_month):
    xml_files = get_xml_files(f"{year_month}")
    return render_template('index.html', year_month=year_month, xml_files=xml_files)


@app.route('/<year_month>/<filename>')
def display_feed(year_month, filename):
    file_url = url_for('static', filename=f"{year_month}/{filename}")
    print(file_url)
    xml_feed = feedparser.parse(file_url)
    print(xml_feed)
    return render_template('feed.html', feed=xml_feed)


if __name__ == '__main__':
    app.run(debug=True)
