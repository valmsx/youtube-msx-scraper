from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
from db import get_conn, init_db
import os

app = Flask(__name__)
init_db()  # Inizializza le tabelle se non esistono

@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

@app.route("/msx_search", methods=["OPTIONS"])
@app.route("/favorites", methods=["OPTIONS"])
@app.route("/favorites/delete", methods=["OPTIONS"])
def handle_options():
    return '', 204

def search_youtube_scrape(query, max_results=20):
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
    }
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    html = res.text

    match = re.search(r"var ytInitialData = ({.*?});</script>", html)
    if not match:
        return []

    data = __import__("json").loads(match.group(1))
    contents = data.get("contents", {})\
        .get("twoColumnSearchResultsRenderer", {})\
        .get("primaryContents", {})\
        .get("sectionListRenderer", {})\
        .get("contents", [])

    items = []
    for section in contents:
        for c in section.get("itemSectionRenderer", {}).get("contents", []):
            vr = c.get("videoRenderer")
            if not vr:
                continue
            vid = vr.get("videoId")
            title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
            thumb = vr.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url", "")
            items.append({
                "title": title,
                "playerLabel": title,
                "image": thumb,
                "action": f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={vid}"
            })
            if len(items) >= max_results:
                break
        if len(items) >= max_results:
            break
    return items

@app.route("/msx_search")
def msx_search():
    query = request.args.get("input", "").strip()
    if not query:
        return jsonify({
            "type": "pages",
            "headline": "YouTube Search",
            "template": {
                "type": "separate",
                "layout": "0,0,3,3",
                "color": "black",
                "imageFiller": "cover"
            },
            "items": []
        })

    try:
        items = search_youtube_scrape(query)
    except Exception as e:
        return jsonify({
            "type": "pages",
            "headline": "Errore scraping",
            "template": {
                "type": "separate",
                "layout": "0,0,3,3",
                "color": "black",
                "imageFiller": "cover"
            },
            "items": [{
                "title": "Errore",
                "playerLabel": "Errore",
                "image": "https://via.placeholder.com/320x180.png?text=Error",
                "action": f"text:{str(e)}"
            }]
        }), 500

    return jsonify({
        "type": "pages",
        "headline": f"Risultati per '{query}'",
        "template": {
            "type": "separate",
            "layout": "0,0,3,3",
            "color": "black",
            "imageFiller": "cover"
        },
        "items": items
    })

# ==========================
# Gestione Preferiti (DB)
# ==========================

@app.route("/favorites", methods=["POST"])
def add_favorite():
    data = request.json
    title = data.get("title")
    url = data.get("url")
    img = data.get("image", "")
    fav_type = data.get("type", "video")

    if not title or not url:
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO favorites (type, title, url, image)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING;
                """, (fav_type, title, url, img))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites", methods=["GET"])
def list_favorites():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, url, image, type FROM favorites;")
                rows = cur.fetchall()
        items = [{
            "title": r[0],
            "action": r[1],
            "image": r[2],
            "playerLabel": r[0]
        } for r in rows]
        return jsonify({
            "type": "pages",
            "headline": "Preferiti",
            "template": {
                "type": "separate",
                "layout": "0,0,3,3",
                "color": "black",
                "imageFiller": "cover"
            },
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites/delete", methods=["POST"])
def delete_favorite():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL mancante"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM favorites WHERE url = %s;", (url,))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
