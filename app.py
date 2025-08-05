from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
import re
from db import get_conn, init_db
import json
from urllib.parse import quote

app = Flask(__name__)
init_db()

# ====================
# CORS SETUP
# ====================
@app.after_request
def apply_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

# ====================
# UTILITY FUNCTIONS
# ====================
def parse_youtube_date(published_text):
    """Converte la data relativa di YouTube (es. '2 anni fa') in data assoluta"""
    if not published_text:
        return ""
    
    now = datetime.now()
    try:
        num = int(published_text.split()[0])
        if "ora" in published_text:
            return (now - timedelta(hours=num)).strftime("%d/%m/%Y")
        elif "giorno" in published_text:
            return (now - timedelta(days=num)).strftime("%d/%m/%Y")
        elif "settimana" in published_text:
            return (now - timedelta(weeks=num)).strftime("%d/%m/%Y")
        elif "mese" in published_text:
            return (now - timedelta(days=num*30)).strftime("%d/%m/%Y")
        elif "anno" in published_text:
            return (now - timedelta(days=num*365)).strftime("%d/%m/%Y")
    except:
        return published_text
    return published_text

def get_view_template(view_type):
    """Restituisce il template in base al tipo di visualizzazione"""
    templates = {
        "grid": {
            "type": "grid",
            "layout": "0,0,2,4",
            "display": "vertical",
            "itemHeight": "medium"
        },
        "list": {
            "type": "list",
            "layout": "0,0,8,1",
            "display": "horizontal",
            "itemHeight": "small"
        },
        "compact": {
            "type": "list",
            "layout": "0,0,10,1",
            "display": "horizontal",
            "itemHeight": "small"
        }
    }
    return templates.get(view_type, templates["grid"])

# ====================
# YOUTUBE SEARCH
# ====================
def search_youtube_scrape(query, max_results=20):
    url = f"https://www.youtube.com/results?search_query={quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    
    match = re.search(r"var ytInitialData = ({.*?});</script>", res.text)
    if not match:
        return []

    data = json.loads(match.group(1))
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
            channel = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "Canale sconosciuto")
            channel_id = vr.get("ownerText", {}).get("runs", [{}])[0].get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
            date = vr.get("publishedTimeText", {}).get("simpleText", "")
            views = vr.get("viewCountText", {}).get("simpleText", "")

            exact_date = parse_youtube_date(date)
            
            items.append({
                "title": title,
                "label": channel,
                "footer": f"{exact_date} • {views}" if exact_date else f"{date} • {views}",
                "image": thumb,
                "action": f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={vid}",
                "buttons": [
                    {
                        "title": "📺 Canale",
                        "action": f"search:replace:http://{request.host}/channel?channel_id={channel_id}"
                    },
                    {
                        "title": "💖 Aggiungi",
                        "action": f"service:http://{request.host}/favorites?action=add&video_id={vid}&title={quote(title)}&channel={quote(channel)}"
                    }
                ]
            })
            if len(items) >= max_results:
                break
        if len(items) >= max_results:
            break
    return items

@app.route("/msx_search", methods=["GET", "OPTIONS"])
def msx_search():
    if request.method == "OPTIONS":
        return '', 204
    
    query = request.args.get("input", "").strip()
    view_type = request.args.get("view", "grid")

    if not query:
        return jsonify({
            "type": "pages",
            "headline": "Ricerca YouTube",
            "template": get_view_template(view_type),
            "items": []
        })

    try:
        items = search_youtube_scrape(query)
    except Exception as e:
        return jsonify({
            "type": "pages",
            "headline": "Errore",
            "items": [{
                "title": "Errore durante la ricerca",
                "label": str(e),
                "image": "https://via.placeholder.com/320x180.png?text=Errore",
                "action": "none"
            }]
        }), 500

    return jsonify({
        "type": "pages",
        "headline": f"Risultati per: {query}",
        "actions": [
            {
                "title": "🔍 Nuova ricerca",
                "action": "search:request"
            },
            {
                "title": "🖼️ Vista Griglia",
                "action": f"search:replace:http://{request.host}/msx_search?input={quote(query)}&view=grid"
            },
            {
                "title": "📋 Vista Lista",
                "action": f"search:replace:http://{request.host}/msx_search?input={quote(query)}&view=list"
            },
            {
                "title": "📜 Vista Compatta",
                "action": f"search:replace:http://{request.host}/msx_search?input={quote(query)}&view=compact"
            }
        ],
        "template": {
            **get_view_template(view_type),
            "color": "#FF0000",
            "imageFiller": "cover",
            "itemLayout": {
                "titleFontSize": "medium",
                "labelFontSize": "small",
                "footerFontSize": "small",
                "titleLines": 2,
                "labelLines": 1
            }
        },
        "items": items
    })

# ====================
# CHANNEL VIDEOS
# ====================
@app.route("/channel", methods=["GET"])
def channel_videos():
    channel_id = request.args.get("channel_id")
    if not channel_id:
        return jsonify({"error": "Manca l'ID del canale"}), 400
    
    # Implementazione reale richiederebbe scraping della pagina del canale
    # Placeholder per dimostrazione
    return jsonify({
        "type": "pages",
        "headline": "Video del Canale",
        "template": get_view_template("grid"),
        "actions": [
            {
                "title": "🔙 Indietro",
                "action": "back"
            }
        ],
        "items": [{
            "title": "Video di esempio del canale",
            "label": "Nome Canale",
            "footer": "01/01/2023 • 1M visualizzazioni",
            "image": "https://via.placeholder.com/320x180",
            "action": "none"
        }]
    })

# ====================
# FAVORITES
# ====================
@app.route("/favorites", methods=["POST"])
def add_favorite():
    data = request.json or request.form
    title = data.get("title")
    url = data.get("url") or f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={data.get('video_id')}"
    img = data.get("image", f"https://img.youtube.com/vi/{data.get('video_id')}/hqdefault.jpg")
    channel = data.get("channel", "")

    if not title or not url:
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO favorites (title, url, image, channel)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING;
                """, (title, url, img, channel))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites", methods=["GET"])
def list_favorites():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, url, image, channel FROM favorites ORDER BY created_at DESC;")
                rows = cur.fetchall()
        
        items = [{
            "title": r[0],
            "label": r[3],
            "image": r[2],
            "action": r[1],
            "buttons": [
                {
                    "title": "❌ Rimuovi",
                    "action": f"service:http://{request.host}/favorites/delete?url={quote(r[1])}"
                }
            ]
        } for r in rows]

        return jsonify({
            "type": "pages",
            "headline": "Preferiti",
            "actions": [
                {
                    "title": "🔙 Indietro",
                    "action": "back"
                }
            ],
            "template": get_view_template("grid"),
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/favorites/delete", methods=["GET", "POST"])
def delete_favorite():
    url = request.args.get("url") or (request.json or request.form).get("url")
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

# ====================
# HISTORY
# ====================
@app.route("/history", methods=["POST"])
def add_history():
    data = request.json or request.form
    title = data.get("title")
    url = data.get("url") or f"video:plugin:http://msx.benzac.de/plugins/youtube.html?id={data.get('video_id')}"
    img = data.get("image", f"https://img.youtube.com/vi/{data.get('video_id')}/hqdefault.jpg")
    channel = data.get("channel", "")

    if not title or not url:
        return jsonify({"error": "Dati mancanti"}), 400

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO history (title, url, image, channel)
                    VALUES (%s, %s, %s, %s);
                """, (title, url, img, channel))
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["GET"])
def list_history():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT title, url, image, channel, created_at 
                    FROM history 
                    ORDER BY created_at DESC
                    LIMIT 50;
                """)
                rows = cur.fetchall()
        
        items = [{
            "title": r[0],
            "label": f"{r[3]} • {r[4].strftime('%d/%m/%Y')}",
            "image": r[2],
            "action": r[1],
            "buttons": [
                {
                    "title": "💖 Aggiungi",
                    "action": f"service:http://{request.host}/favorites?action=add&title={quote(r[0])}&url={quote(r[1])}"
                }
            ]
        } for r in rows]

        return jsonify({
            "type": "pages",
            "headline": "Cronologia",
            "actions": [
                {
                    "title": "🔙 Indietro",
                    "action": "back"
                },
                {
                    "title": "🗑️ Pulisci",
                    "action": f"service:http://{request.host}/history/clear"
                }
            ],
            "template": get_view_template("list"),
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/history/clear", methods=["POST"])
def clear_history():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM history;")
                conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
