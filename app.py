from datetime import datetime
import calendar
import os
import openai
from dotenv import load_dotenv
from flask import Flask, request, Response, render_template, url_for, abort, send_file
import feedparser
import xml.etree.ElementTree as ET
from flask_frozen import Freezer
import re
from flask import Flask
from markupsafe import Markup
import shutil
import nltk

from src.logger import setup_logger

logger = setup_logger()

load_dotenv()
openai.api_key = os.environ.get("OPENAI_API_KEY")

app = Flask(__name__, static_url_path='', static_folder='css')


# app.config['SECRET_KEY'] = os.environ.get("FLASK_SECRET")
def linkify(text):
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+(?<!\.)')
    return Markup(url_pattern.sub(r'<a href="\g<0>">\g<0></a>', text))


def remove_unfinished_sentences(text):
    try:
        sentences = nltk.sent_tokenize(text)
        if not sentences[-1].endswith(('.', '!', '?')):
            sentences = sentences[:-1]
        text = ' '.join(sentences)
    except Exception as ex:
        print(f"Error: {ex}")
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+(?<!\.)')
    return Markup(url_pattern.sub(r'<a href="\g<0>">\g<0></a>', text))


# app.jinja_env.filters['linkify'] = linkify
app.jinja_env.filters['remove_unfinished'] = remove_unfinished_sentences
app.config['FREEZER_DEFAULT_URL_GENERATOR'] = 'flask_frozen.url_generators.default_url_generator_with_html'
freezer = Freezer(app)


@freezer.register_generator
def url_generator():
    build_path = os.path.join(app.root_path, "build")
    yield from generate_url_list(build_path)


def save_static_html(endpoint, dev_name, year_month, type_by, build_path):
    with app.app_context():
        folder = f'static/{dev_name}/{year_month}'
        posts, min_date, max_date = parse_xml_files(folder)

        if type_by == "thread":
            posts = sorted(posts, key=lambda p: p['author'])
        elif type_by == "subject":
            posts = sorted(posts, key=lambda p: p['title'])
        elif type_by == "date":
            posts = sorted(posts, key=lambda p: p['date'])
        elif type_by == "author":
            posts = sorted(posts, key=lambda p: p['author'])
        else:
            raise ValueError(f"Invalid type_by: {type_by}")

        html = render_template('thread.html', posts=posts, year_month=year_month, min_date=min_date, max_date=max_date,
                               type_by=type_by)

        html_folder_path = os.path.join(build_path, endpoint)
        os.makedirs(html_folder_path, exist_ok=True)
        html_file_path = os.path.join(html_folder_path, f"{year_month}.html")

        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html)


def save_static_xml(dev_name, year_month, filename, build_path):
    original_file_path = os.path.join(app.root_path, f"static/{dev_name}/{year_month}/{filename}")
    xml_folder_path = os.path.join(build_path, dev_name, year_month)
    os.makedirs(xml_folder_path, exist_ok=True)
    xml_file_path = os.path.join(xml_folder_path, filename)

    shutil.copyfile(original_file_path, xml_file_path)


def generate_url_list(build_path=None):
    url_list = []
    data = get_year_month_data()

    for row in data:
        year_month = row["month"].replace(" ", "_")
        folder = f'static/{row["dev_name"]}/{year_month}'

        # Check if the folder exists
        if os.path.isdir(os.path.join(app.root_path, folder)):
            for type_by in ["thread", "subject", "author", "date"]:
                save_static_html(type_by, row["dev_name"], year_month, type_by, build_path)

            url_list.append(url_for("thread", dev_name=row["dev_name"], year_month=year_month))
            url_list.append(url_for("subject", dev_name=row["dev_name"], year_month=year_month))
            url_list.append(url_for("author", dev_name=row["dev_name"], year_month=year_month))
            url_list.append(url_for("date", dev_name=row["dev_name"], year_month=year_month))

            posts, _, _ = parse_xml_files(folder)
            for post in posts:
                save_static_xml(row["dev_name"], year_month, post["filename"], build_path)
                url_list.append(
                    url_for("display_feed", dev_name=row["dev_name"], year_month=year_month, filename=post["filename"]))

    return url_list


def parse_xml_files(folder):
    files = os.listdir(os.path.join(app.root_path, folder))
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
    month_order = {
        'Jan': 1,
        'Feb': 2,
        'March': 3,
        'April': 4,
        'May': 5,
        'June': 6,
        'July': 7,
        'Aug': 8,
        'Sept': 9,
        'Oct': 10,
        'Nov': 11,
        'Dec': 12
    }

    folders = os.listdir(os.path.join(app.root_path, 'static'))
    data = []
    for dev_folder in folders:
        if os.path.isdir(os.path.join(app.root_path, f'static/{dev_folder}')):
            for f in os.listdir(os.path.join(app.root_path, f'static/{dev_folder}')):
                month = f.split("_")[0]
                year = f.split("_")[-1]
                data.append({"month": f"{month} {year}", "dev_name": str(dev_folder)})
    data_sorted = sorted(data, key=lambda x: (int(x['month'].split()[1]),
                                              (month_order[x['month'].split()[0]])), reverse=True)

    return data_sorted


@app.route("/")
def archive():
    data = get_year_month_data()
    return render_template('index.html', data=data)


def sort_grouping(posts):
    '''
    diff between filename and title

    for combined file
    # filename = combined_BIP-20-Rejected-process-for-BIP-21N.xml
    # title = Combined summary - BIP-20-Rejected-process-for-BIP-21N

    for simple file
    # filename = 001234_BIP-20-Rejected-process-for-BIP-21N.xml
    # title = BIP-20-Rejected-process-for-BIP-21N

    '''

    combined = {}
    threads = []
    for post in posts:
        if "combined_" in post['filename']:
            ckey = '_'.join(post['filename'].split("_")[1:])
            combined[ckey] = post
        else:
            threads.append(post)

    sorted_threads = sorted(threads, key=lambda x: x['title'])
    for i, thread in enumerate(sorted_threads):
        ckey = '_'.join(thread['filename'].split("_")[1:])
        if ckey in combined:
            sorted_threads.insert(i, combined[ckey])
            combined.pop(ckey)

    return sorted_threads


def sort_and_grouping(posts):
    combined = {}
    for post in posts:
        if "combined_" in post['filename']:
            ckey = '_'.join(post['filename'].split("_")[1:])
            combined[ckey] = post
    sorted_threads = sorted(posts, key=lambda x: x['title'])
    new_threads = []
    for thread in sorted_threads:
        if "combined_" not in thread['filename']:
            ckey = '_'.join(thread['filename'].split("_")[1:])
            if ckey not in combined:
                new_threads.append(thread)
        else:
            new_threads.append(thread)

    return new_threads


@app.route('/thread/<dev_name>/<year_month>.html')
def thread(dev_name, year_month):
    try:
        folder = f'static/{dev_name}/{year_month}'
        posts, min_date, max_date = parse_xml_files(folder)
        posts = sort_and_grouping(posts)
        return render_template('thread.html', posts=posts, dev_name=dev_name, year_month=year_month, min_date=min_date,
                               max_date=max_date, type_by="thread")
    except Exception as e:
        logger.exception(e)
        abort(500)


@app.route('/author/<dev_name>/<year_month>.html')
def author(dev_name, year_month):
    folder = f'static/{dev_name}/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['author'])
    return render_template('thread.html', posts=posts, dev_name=dev_name, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="author")


@app.route('/subject/<dev_name>/<year_month>.html')
def subject(dev_name, year_month):
    folder = f'static/{dev_name}/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['title'])
    return render_template('thread.html', posts=posts, dev_name=dev_name, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="subject")


@app.route('/date/<dev_name>/<year_month>.html')
def date(dev_name, year_month):
    folder = f'static/{dev_name}/{year_month}'
    posts, min_date, max_date = parse_xml_files(folder)
    posts = sorted(posts, key=lambda p: p['date'])
    return render_template('thread.html', posts=posts, dev_name=dev_name, year_month=year_month, min_date=min_date,
                           max_date=max_date, type_by="date")


@app.route('/<dev_name>/<year_month>/<filename>.html')
def display_feed(dev_name, year_month, filename):
    filename = filename + ".xml"
    file_url = f"./static/{dev_name}/{year_month}/{filename}"
    xml_feed = feedparser.parse(file_url)
    combined_filename = "combined_" + "_".join(filename.split("_")[1:])
    if combined_filename in os.listdir(os.path.join("./static", str(dev_name), str(year_month))):
        return render_template('feed.html', feed=xml_feed, dev_name=dev_name, year_month=year_month,
                               filename=combined_filename)
    else:
        return render_template('feed.html', feed=xml_feed, dev_name=dev_name, year_month=year_month,
                               filename=filename)


@app.route('/<dev_name>/<year_month>/<filename>')
def display_xml(dev_name, year_month, filename):
    original_file_path = f"./static/{dev_name}/{year_month}/{filename}"
    combined_filename = "combined_" + "_".join(filename.split("_")[1:])
    combined_file_path = f"./static/{dev_name}/{year_month}/{combined_filename}"

    if os.path.exists(original_file_path):
        file_path = original_file_path
    elif os.path.exists(combined_file_path):
        file_path = combined_file_path
    else:
        return f"Error: {filename} not found in {year_month}", 404

    return send_file(file_path, mimetype='text/xml')


if __name__ == '__main__':
    import sys
    nltk.download('punkt')

    if len(sys.argv) > 1 and sys.argv[1] == "build":
        freezer.freeze()
    else:
        os.popen('python scheduler.py > scheduler_logs.txt 2>&1 &')
        try:
            app.run(debug=True)
        except Exception as e:
            logger.exception(e)
