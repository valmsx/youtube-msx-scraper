from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
from db import get_conn, init_db
import os

app = Flask(__name__)
init_db()

# ============================
# CORS per SmartTV + GitHub Pages
# ============================
# ORIGINI CONSENTITE (aggiungi anche altri domini se necessario)
ALLOWED_ORIGINS = [
    "https://msx.benzac.de",
    "https://valmsx.github.io",              # se usi GitHub Pages
    "https://youtube-plugin-flask.onrender.com"  # utile se chiami da browser
]

@app.after_request
def apply_cors(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


# ============================
# Gestione OPTIONS preflight
# ============================
@app.route("/<path:path>", methods=["OPTIONS"])
def handle_options_all(path):
    return '', 204

@app.route("/ping")
def ping():
    return jsonify({"message": "pong"})

# ============================
# Ricerca YouTube con scraping
# ============================
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

        # Salva nella cronologia
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO history (query) VALUES (%s)
                        ON CONFLICT (query) DO UPDATE SET timestamp = CURRENT_TIMESTAMP;
                    """, (query,))
                    conn.commit()
        except Exception as db_error:
            print(f"[WARN] Errore salvataggio history: {db_error}")

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

# ============================
# Gestione Preferiti
# ============================
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

# ============================
# Cronologia
# ============================
@app.route("/history", methods=["GET"])
def get_history():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT query FROM history ORDER BY timestamp DESC LIMIT 30;")
                rows = cur.fetchall()
        items = [{
            "title": r[0],
            "playerLabel": r[0],
            "action": f"content:https://youtube-plugin-flask.onrender.com/msx_search?input={requests.utils.quote(r[0])}",
            "image": "https://via.placeholder.com/320x180.png?text=History"
        } for r in rows]
        return jsonify({
            "type": "pages",
            "headline": "Ricerche recenti",
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

@app.route("/history/delete", methods=["POST"])
def delete_history_item():
    data = request.json
    query = data.get("query")
    if not query:
        return jsonify({"error": "Parametro 'query' mancante"}), 400
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM history WHERE query = %s;", (query,))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
