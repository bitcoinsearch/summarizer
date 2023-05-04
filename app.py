from datetime import datetime
import os
import openai
from dotenv import load_dotenv
from flask import Flask, request, Response, render_template, url_for
import feedparser
import warnings
import xml.etree.ElementTree as ET

print("Started scheduler...")
os.popen('python scheduler.py > scheduler_logs.txt 2>&1 &')
warnings.filterwarnings("ignore")

load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")

app = Flask(__name__)


def parse_xml_files(folder):
    files = os.listdir(folder)
    posts = []
    namespace = {'atom': 'http://www.w3.org/2005/Atom'}

    for file in files:
        if file.endswith('.xml'):
            tree = ET.parse(os.path.join(folder, file))
            root = tree.getroot()

            title = root.find('atom:title', namespace).text
            author = root.find('atom:author/atom:name', namespace).text
            date = root.find('atom:entry/atom:published', namespace).text
            # summary = root.find('atom:entry/atom:summary', namespace).text

            posts.append({'title': title, 'author': author, 'date': date, 'filename': file})

    min_date = min(posts, key=lambda x: x['date'])['date']
    max_date = max(posts, key=lambda x: x['date'])['date']
    min_date_dt = datetime.fromisoformat(min_date)
    max_date_dt = datetime.fromisoformat(max_date)

    return posts, min_date_dt, max_date_dt


def get_year_month_data():
    folders = os.listdir(os.path.join(app.root_path, 'static'))
    data = []
    for f in folders:
        month = f.split("_")[0]
        year = f.split("_")[-1]
        data.append({"month": f"{month} {year}"})
    return data


@app.route("/")
def archive():
    data = get_year_month_data()
    return render_template('archive.html', data=data)


@app.route('/thread/<year_month>')
def thread(year_month):
    folder = f'static/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['author'])
    return render_template('thread.html', posts=posts, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="thread")


@app.route('/author/<year_month>')
def author(year_month):
    folder = f'static/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['author'])
    return render_template('thread.html', posts=posts, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="author")


@app.route('/subject/<year_month>')
def subject(year_month):
    folder = f'static/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['title'])
    return render_template('thread.html', posts=posts, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="subject")


@app.route('/date/<year_month>')
def date(year_month):
    folder = f'static/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['date'])
    return render_template('thread.html', posts=posts, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="date")


@app.route('/<year_month>/<filename>')
def display_feed(year_month, filename):
    file_url = f"./static/{year_month}/{filename}"
    xml_feed = feedparser.parse(file_url)
    return render_template('feed.html', feed=xml_feed)


if __name__ == '__main__':
    app.run(debug=True)
