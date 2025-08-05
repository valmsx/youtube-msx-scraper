from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import sqlite3
import os

app = Flask(__name__, static_folder="static")
CORS(app)

DB_FILE = "data.db"
os.makedirs("static", exist_ok=True)

# --- Database ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT,
            image TEXT,
            type TEXT,
            video_id TEXT,
            channel TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Funzione per estrarre video_id ---
def extract_video_id(url):
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    return match.group(1) if match else url  # fallback

# --- Ricerca YouTube ---
def search_youtube_scrape(query):
    headers = {"User-Agent": "Mozilla/5.0"}
    params = {"search_query": query}
    url = "https://www.youtube.com/results"
    r = requests.get(url, params=params, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    scripts = soup.find_all("script")
    json_data = None
    for script in scripts:
        if "var ytInitialData" in script.text:
            json_text = script.text.split(" = ", 1)[1].rsplit(";", 1)[0]
            try:
                import json
                json_data = json.loads(json_text)
                break
            except Exception:
                pass

    if not json_data:
        return []

    items = []
    contents = json_data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}) \
        .get("primaryContents", {}).get("sectionListRenderer", {}) \
        .get("contents", [])[0].get("itemSectionRenderer", {}).get("contents", [])

    for video in contents:
        video_renderer = video.get("videoRenderer")
        if not video_renderer:
            continue
        video_id = video_renderer.get("videoId")
        title = video_renderer.get("title", {}).get("runs", [{}])[0].get("text", "No Title")
        thumbnail_url = video_renderer.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url")

        items.append({
            "type": "video",
            "title": title,
            "thumbnail": thumbnail_url,
            "id": video_id,
            "channel": "",
            "actions": [{
                "action": "youtube:play",
                "label": "Play",
                "payload": {"videoId": video_id}
            }]
        })

    return items

# --- API: Ricerca MSX ---
@app.route("/msx_search")
def msx_search():
    query = request.args.get("input", "")
    if not query:
        return jsonify({"type": "pages", "headline": "Risultati", "contents": []})
    
    results = search_youtube_scrape(query)
    return jsonify({
        "type": "pages",
        "headline": f"Risultati per '{query}'",
        "contents": results
    })

# --- API: GET Preferiti ---
@app.route("/favorites", methods=["GET"])
def list_favorites():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT title, url, image, type, video_id, COALESCE(channel, '') as channel
        FROM favorites
    """).fetchall()
    conn.close()

    contents = []
    for r in rows:
        video_id = r['video_id'] or extract_video_id(r['url'])
        contents.append({
            "type": "video",
            "title": r['title'],
            "thumbnail": r['image'],
            "id": video_id,
            "channel": r['channel'],
            "actions": [{
                "action": "youtube:play",
                "label": "Play",
                "payload": {"videoId": video_id}
            }]
        })

    return jsonify({
        "type": "pages",
        "headline": "Preferiti",
        "contents": contents
    })

# --- API: Aggiungi Preferito ---
@app.route("/favorites", methods=["POST"])
def add_favorite():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid data"}), 400

    video_id = data.get("videoId", "")
    title = data.get("title", "")
    image = data.get("image", "")
    type_ = data.get("type", "")
    channel = data.get("channel", "")

    if not video_id or not title:
        return jsonify({"error": "Missing fields"}), 400

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO favorites (title, url, image, type, video_id, channel)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, f"https://youtube.com/watch?v={video_id}", image, type_, video_id, channel))
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# --- Static files (MSX interaction plugin page) ---
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# --- Health check ---
@app.route("/ping")
def ping():
    return "pong"

# --- Start ---
if __name__ == "__main__":
    app.run(debug=True)
